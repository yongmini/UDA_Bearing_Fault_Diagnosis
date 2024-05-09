'''
Paper: Wang, Q., Taal, C. and Fink, O., 2021. Integrating expert knowledge with domain adaptation 
    for unsupervised fault diagnosis. IEEE Transactions on Instrumentation and Measurement, 71, pp.1-12.
Reference code: https://github.com/qinenergy/syn2real
Note: Augmented Conditional Domain Alignment Neural Network (ACDANN) was not an official name in the paper.
'''
import torch
import logging
import numpy as np
from tqdm import tqdm
import torch.nn.functional as F
from collections import defaultdict
import wandb
import utils
import model_base
from train_utils import InitTrain
from utils import visualize_tsne_and_confusion_matrix
import numpy as np     
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
import os

class Trainset(InitTrain):
    
    def __init__(self, args):
        super(Trainset, self).__init__(args)
        feature_size = 2560
        self.model = model_base.BaseModel_add_freq(input_size=1, num_classes=args.num_classes,feature_size=feature_size,
                                      dropout=args.dropout).to(self.device)
        self.grl = utils.GradientReverseLayer()
        self.dist_beta = torch.distributions.beta.Beta(1., 1.)
        self.model = model_base.BaseModel_add_freq(input_size=1, num_classes=args.num_classes,
                                          dropout=args.dropout).to(self.device)
        self._init_data()
    
    def save_model(self):
        torch.save({
            'model': self.model.state_dict()
            }, self.args.save_path + '.pth')
        logging.info('Model saved to {}'.format(self.args.save_path + '.pth'))
    
    def load_model(self):
        logging.info('Loading model from {}'.format(self.args.load_path))
        ckpt = torch.load(self.args.load_path)
        self.model.load_state_dict(ckpt['model'])
        
    def train(self):
        args = self.args
        
        if args.train_mode == 'single_source':
            src = args.source_name[0]
        elif args.train_mode == 'source_combine':
            src = args.source_name
        elif args.train_mode == 'multi_source':
            raise Exception("This model cannot be trained in multi_source mode.")
        
        self.optimizer = self._get_optimizer([self.model, self.discriminator])
        self.lr_scheduler = self._get_lr_scheduler(self.optimizer)
        
        best_acc = 0.0
        best_epoch = 0
   
        for epoch in range(1, args.max_epoch+1):
            logging.info('-'*5 + 'Epoch {}/{}'.format(epoch, args.max_epoch) + '-'*5)
            
            # Update the learning rate
            if self.lr_scheduler is not None:
                logging.info('current lr: {}'.format(self.lr_scheduler.get_last_lr()))
   
            # Each epoch has a training and val phase
            epoch_acc = defaultdict(float)
   
            # Set model to train mode or evaluate mode
            self.model.train()
            self.discriminator.train()
            epoch_loss = defaultdict(float)
            tradeoff = self._get_tradeoff(args.tradeoff, epoch) 
            
            num_iter = len(self.dataloaders['train'])
            for i in tqdm(range(num_iter), ascii=True):
                target_data, target_labels = utils.get_next_batch(self.dataloaders,
                						 self.iters, 'train', self.device)
                source_data, source_labels = utils.get_next_batch(self.dataloaders,
            						     self.iters, src, self.device)
                # forward
                batch_size = source_data.shape[0]
                self.optimizer.zero_grad()
                data = torch.cat((source_data, target_data), dim=0)
                
                y, f = self.model(data)
                f_s, f_t = f.chunk(2, dim=0)
                y_s, y_t = y.chunk(2, dim=0)
                
                loss_c = F.cross_entropy(y_s, source_labels)
                
                softmax_output_src = F.softmax(y_s, dim=-1)
                softmax_output_tgt = F.softmax(y_t, dim=-1)
               
                lmb = self.dist_beta.sample((batch_size, 1)).to(self.device)
                labels_dm = torch.concat((torch.ones(batch_size, dtype=torch.long),
                      torch.zeros(batch_size, dtype=torch.long)), dim=0).to(self.device)
        
                idxx = np.arange(batch_size)
                np.random.shuffle(idxx)
                f_s = lmb * f_s + (1.-lmb) * f_s[idxx]
                f_t = lmb * f_t + (1.-lmb) * f_t[idxx]
    
                softmax_output_src = lmb * softmax_output_src + (1.-lmb) * softmax_output_src[idxx]
                softmax_output_tgt = lmb * softmax_output_tgt + (1.-lmb) * softmax_output_tgt[idxx]
                                             
                feat_src_ = torch.bmm(softmax_output_src.unsqueeze(2),
                                     f_s.unsqueeze(1)).view(batch_size, -1)
                feat_tgt_ = torch.bmm(softmax_output_tgt.unsqueeze(2),
                                     f_t.unsqueeze(1)).view(batch_size, -1)
    
                feat = self.grl(torch.concat((feat_src_, feat_tgt_), dim=0))
                logits_dm = self.discriminator(feat)
                loss_dm = F.cross_entropy(logits_dm, labels_dm)
                loss = loss_c + tradeoff[0] * loss_dm

          
                
                epoch_acc['Source Data']  += utils.get_accuracy(y_s, source_labels)
                epoch_acc['Discriminator']  += utils.get_accuracy(logits_dm, labels_dm)
                
                epoch_loss['Source Classifier'] += loss_c
                epoch_loss['Discriminator'] += loss_dm

                # backward
                loss.backward()
                self.optimizer.step()
            
            # Print the train and val information via each epoch
            for key in epoch_acc.keys():
                avg_acc = epoch_acc[key] / num_iter
                logging.info('Train-Acc {}: {:.4f}'.format(key, avg_acc))
                wandb.log({f'Train-Acc {key}': avg_acc}, commit=False)  # Log to wandb
            for key in epoch_loss.keys():
                logging.info('Train-Loss {}: {:.4f}'.format(key, epoch_loss[key]/num_iter))
            # log the best model according to the val accuracy
            new_acc = self.test()

            last_acc_formatted = f"{new_acc:.3f}"
            wandb.log({"last_target_acc": float(last_acc_formatted)})
            
            
            if new_acc >= best_acc:
                best_acc = new_acc
                best_epoch = epoch
            logging.info("The best model epoch {}, val-acc {:.4f}".format(best_epoch, best_acc))
            
            best_acc_formatted = f"{best_acc:.3f}"
            wandb.log({"best_target_acc": float(best_acc_formatted)})
            
            if self.lr_scheduler is not None:
                self.lr_scheduler.step()
    
            # self.epoch = epoch
            # if epoch == 1 or epoch % 5 == 0:
            #     self.test_tsne()
                
        if self.args.tsne:
                self.test_tsne()
              #  self.test_tsne_all()
        acc=self.test()
        acc_formatted = f"{acc:.3f}"
        wandb.log({"correct_target_acc": float(acc_formatted)})        
    def test(self):
        self.model.eval()
        acc = 0.0
        iters = iter(self.dataloaders['val'])
        num_iter = len(iters)
        with torch.no_grad():
            for i in tqdm(range(num_iter), ascii=True):
                target_data, target_labels, _ = next(iters)
                target_data, target_labels = target_data.to(self.device), target_labels.to(self.device)
                pred = self.model(target_data)
                acc += utils.get_accuracy(pred, target_labels)
        acc /= num_iter
        logging.info('Val-Acc Target Data: {:.4f}'.format(acc))
        return acc
    
    
    def test_tsne(self):
        self.model.eval()
        acc = 0.0
        
        
        self.dataloaders2 = {x: torch.utils.data.DataLoader(self.datasets[x],
                                                        batch_size=64,
                                                        shuffle=False,
                                                        drop_last=False,
                                                        pin_memory=(True if self.device == 'cuda' else False))
                            for x in ['train']}

                
        
   
        iters = iter(self.dataloaders2['train'])#val
        num_iter = len(iters)
        all_features = []
        all_labels = []
        all_preds = [] 
        with torch.no_grad():
            for i in tqdm(range(num_iter), ascii=True):
                target_data, target_labels, _ = next(iters)
                target_data, target_labels = target_data.to(self.device), target_labels.to(self.device)
                pred, features = self.model(target_data)
                
                pred=pred.argmax(dim=1)
                all_features.append(features.cpu().numpy())
                all_labels.append(target_labels.cpu().numpy())
                all_preds.append(pred.cpu().numpy())

        # Concatenate features and labels
        all_features = np.concatenate(all_features, axis=0)
        all_labels = np.concatenate(all_labels, axis=0)
        all_preds = np.concatenate(all_preds, axis=0)
        
        cm = confusion_matrix(all_labels, all_preds)

        # Perform t-SNE and save plot
        filename = f"tsne_conmat_imba_{str(self.args.imba)}_{self.args.model_name}_{self.epoch}.png"
        visualize_tsne_and_confusion_matrix(all_features, all_labels,all_preds, cm, self.args.save_dir,filename)
        
        

            