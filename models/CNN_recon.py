import torch
import logging
from tqdm import tqdm
import torch.nn.functional as F
from collections import defaultdict
import wandb
import utils
import model_base
from train_utils import InitTrain
import numpy as np        
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.manifold import TSNE
import os
from utils import visualize_tsne_and_confusion_matrix
from sklearn.metrics import confusion_matrix

class Trainset(InitTrain):
    
    def __init__(self, args):
        super(Trainset, self).__init__(args)

        
        self.model = model_base.BaseModelRecon(input_size=1, num_classes=args.num_classes,
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
        
        self.optimizer = self._get_optimizer(self.model)
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
            epoch_loss = defaultdict(float)
        
            num_iter = len(self.dataloaders[src])               
            for i in tqdm(range(num_iter), ascii=True):
                source_data, source_labels = utils.get_next_batch(self.dataloaders,
                                            self.iters, src, self.device)
                # forward
                self.optimizer.zero_grad()
                pred, _ ,recon = self.model(source_data)
                cls_loss = F.cross_entropy(pred, source_labels)
                reconst_loss = F.binary_cross_entropy(recon, source_data, reduction='sum')
                loss = cls_loss + reconst_loss
                epoch_acc['Source Data']  += utils.get_accuracy(pred, source_labels)
                epoch_loss['reconst_loss'] += reconst_loss
                epoch_loss['Source Classifier'] += loss

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
            # if epoch == 1 or epoch % 50 == 0:
            #     self.test_tsne()
        acc=self.test()
        acc_formatted = f"{acc:.3f}"
        wandb.log({"target_acc": float(acc_formatted)})            
        # if self.args.tsne:
        #         self.test_tsne()
        #       #  self.test_tsne_all()
            
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
                            for x in ['val','train']}

                
   
        iters = iter(self.dataloaders2['val'])#val
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
        