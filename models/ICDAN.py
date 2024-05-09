'''
Paper: Long, M., Cao, Z., Wang, J. and Jordan, M.I., 2018. Conditional adversarial
    domain adaptation. Advances in neural information processing systems, 31.
Reference code: https://github.com/thuml/Transfer-Learning-Library
'''
import torch
import logging
from tqdm import tqdm
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from collections import defaultdict
import wandb
import utils
import model_base
from train_utils import InitTrain
from utils import visualize_tsne_and_confusion_matrix, I_Softmax
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
import os


def entropy(predictions: torch.Tensor, reduction='none') -> torch.Tensor:

    epsilon = 1e-5
    H = -predictions * torch.log(predictions + epsilon)
    H = H.sum(dim=1)
    if reduction == 'mean':
        return H.mean()
    else:
        return H


class RandomizedMultiLinearMap(nn.Module):

    def __init__(self, features_dim: int, num_classes: int, output_dim: int = 1024):
        super(RandomizedMultiLinearMap, self).__init__()
        self.Rf = torch.randn(features_dim, output_dim)
        self.Rg = torch.randn(num_classes, output_dim)
        self.output_dim = output_dim

    def forward(self, f: torch.Tensor, g: torch.Tensor) -> torch.Tensor:
        f = torch.mm(f, self.Rf.to(f.device))
        g = torch.mm(g, self.Rg.to(g.device))
        output = torch.mul(f, g) / np.sqrt(float(self.output_dim))
        return output


class MultiLinearMap(nn.Module):

    def __init__(self):
        super(MultiLinearMap, self).__init__()

    def forward(self, f: torch.Tensor, g: torch.Tensor) -> torch.Tensor:
        batch_size = f.size(0)
        output = torch.bmm(g.unsqueeze(2), f.unsqueeze(1))
        return output.view(batch_size, -1)
    

class ConditionalDomainAdversarialLoss(nn.Module):
   
    def __init__(self, domain_discriminator: nn.Module, entropy_conditioning: bool = False,
                 randomized: bool = False, num_classes: int = -1,
                 features_dim: int = -1, randomized_dim: int = 1024,
                 reduction: str = 'mean', sigmoid=True, grl = None):
        super(ConditionalDomainAdversarialLoss, self).__init__()
        self.domain_discriminator = domain_discriminator
        self.grl = utils.WarmStartGradientReverseLayer(alpha=1., lo=0., hi=1., max_iters=1000, auto_step=True) \
                                                                                        if grl is None else grl
        self.entropy_conditioning = entropy_conditioning
        self.sigmoid = sigmoid
        self.reduction = reduction

        if randomized:
            assert num_classes > 0 and features_dim > 0 and randomized_dim > 0
            self.map = RandomizedMultiLinearMap(features_dim, num_classes, randomized_dim)
        else:
            self.map = MultiLinearMap()
        self.bce = lambda input, target, weight: F.binary_cross_entropy(input, target, weight,
                                                                        reduction=reduction) if self.entropy_conditioning \
            else F.binary_cross_entropy(input, target, reduction=reduction)
        self.domain_discriminator_accuracy = None

    def forward(self, g_s: torch.Tensor, f_s: torch.Tensor, g_t: torch.Tensor, f_t: torch.Tensor) -> torch.Tensor:
        f = torch.cat((f_s, f_t), dim=0)
        g = torch.cat((g_s, g_t), dim=0)
        g = F.softmax(g, dim=1).detach()
        h = self.grl(self.map(f, g))
        d = self.domain_discriminator(h)

        weight = 1.0 + torch.exp(-entropy(g))
        batch_size = f.size(0)
        weight = weight / torch.sum(weight) * batch_size

        if self.sigmoid:
            d_label = torch.cat((
                torch.ones((g_s.size(0), 1)).to(g_s.device),
                torch.zeros((g_t.size(0), 1)).to(g_t.device),
            ))
            self.domain_discriminator_accuracy = utils.binary_accuracy(d, d_label)
            if self.entropy_conditioning:
                return F.binary_cross_entropy(d, d_label, weight.view_as(d), reduction=self.reduction)
            else:
                return F.binary_cross_entropy(d, d_label, reduction=self.reduction)
        else:
            d_label = torch.cat((
                torch.ones((g_s.size(0), )).to(g_s.device),
                torch.zeros((g_t.size(0), )).to(g_t.device),
            )).long()
            self.domain_discriminator_accuracy = utils.get_accuracy(d, d_label)
            if self.entropy_conditioning:
                raise NotImplementedError("entropy_conditioning")
            return F.cross_entropy(d, d_label, reduction=self.reduction)


class Trainset(InitTrain):
    
    def __init__(self, args):
        super(Trainset, self).__init__(args)
        output_size = 512
        self.domain_discri = model_base.ClassifierMLP(input_size=output_size * args.num_classes, output_size=1,
                        dropout=args.dropout, last='sigmoid').to(self.device)
        grl = utils.GradientReverseLayer() 
        self.domain_adv = ConditionalDomainAdversarialLoss(self.domain_discri, grl=grl)
        self.model = model_base.BaseModel(input_size=1, num_classes=args.num_classes,
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
            raise Exception("This model cannot be trained with multi-source data.")

        self.optimizer = self._get_optimizer([self.model, self.domain_discri])
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
            self.domain_discri.train()
            epoch_loss = defaultdict(float)
            tradeoff = self._get_tradeoff(args.tradeoff, epoch) 
            
            num_iter = len(self.dataloaders['train'])               
            for i in tqdm(range(num_iter), ascii=True):
                target_data, target_labels = utils.get_next_batch(self.dataloaders,
                						 self.iters, 'train', self.device)                    
                source_data, source_labels = utils.get_next_batch(self.dataloaders,
            						     self.iters, src, self.device)
                # forward
                self.optimizer.zero_grad()
                data = torch.cat((source_data, target_data), dim=0)
                
                y, f = self.model(data)
                f_s, f_t = f.chunk(2, dim=0)
                y_s, y_t = y.chunk(2, dim=0)
        
        
                _, _, clc_loss_step = I_Softmax(2, 16, y_s, source_labels,self.device).forward()
             
                loss_c = clc_loss_step
                
        
                loss_d = self.domain_adv(y_s, f_s, y_t, f_t)
                loss = loss_c + tradeoff[0] * loss_d
                epoch_acc['Source Data']  += utils.get_accuracy(y_s, source_labels)
 
                epoch_acc['Discriminator']  += self.domain_adv.domain_discriminator_accuracy
                
                epoch_loss['Source Classifier'] += loss_c
                epoch_loss['Discriminator'] += loss_d

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
            
       #   @  log the best model according to the val accuracy
            new_acc = self.test()
            
            last_acc_formatted = f"{new_acc:.2f}"
            wandb.log({"last_target_acc": float(last_acc_formatted)})
            
            
            if new_acc >= best_acc:
                best_acc = new_acc
                best_epoch = epoch
            logging.info("The best model epoch {}, val-acc {:.4f}".format(best_epoch, best_acc))
            
            best_acc_formatted = f"{best_acc:.2f}"
            wandb.log({"best_target_acc": float(best_acc_formatted)})
    
            
            
            
            if self.lr_scheduler is not None:
                self.lr_scheduler.step()
                             
            if self.args.tsne:
                self.epoch = epoch
                if epoch == 1 or epoch % 5 == 0:
                    self.test_tsne()
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
        iters = iter(self.dataloaders['val'])
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
        filename = "tsne_conmat.png"
        visualize_tsne_and_confusion_matrix(all_features, all_labels, cm, self.args.save_dir,filename)
        
        
    # def test_tsne_all(self):
    #     self.model.eval()
    #     source_iter = iter(self.dataloaders[self.args.source_name[0]])  # Source data iterator 추가
    #     target_iter = iter(self.dataloaders['val'])
        
    #     all_features = []
    #     all_labels = []
    #     all_domains = []  # Source인지 Target인지를 구분하는 레이블 추가
        
    #     with torch.no_grad():
    #         for _ in range(len(target_iter)):
    #             source_data, source_labels ,_ = next(source_iter)
    #             target_data, target_labels, _ = next(target_iter)
                
    #             source_data, source_labels = source_data.to(self.device), source_labels.to(self.device)
    #             target_data, target_labels = target_data.to(self.device), target_labels.to(self.device)
                
    #             _, source_features = self.model(source_data)
    #             _, target_features = self.model(target_data)
                
    #             all_features.append(source_features.cpu().numpy())
    #             all_features.append(target_features.cpu().numpy())
                
    #             all_labels.append(source_labels.cpu().numpy())
    #             all_labels.append(target_labels.cpu().numpy())
                
    #             all_domains.append(np.zeros_like(source_labels.cpu().numpy()))  # Source는 0
    #             all_domains.append(np.ones_like(target_labels.cpu().numpy()))   # Target은 1
        
    #     all_features = np.concatenate(all_features, axis=0)
    #     all_labels = np.concatenate(all_labels, axis=0)
    #     all_domains = np.concatenate(all_domains, axis=0)
        
        
        
    #     tsne = TSNE(n_components=2, perplexity=30, random_state=42)
    #     features_tsne = tsne.fit_transform(all_features)
        
    #     # 시각화를 위한 색상 맵 설정
    #     num_classes = len(np.unique(all_labels))
    #     colors = plt.cm.rainbow(np.linspace(0, 1, num_classes))
        
    #     # Source와 Target에 대한 t-SNE 그래프 그리기
    #     fig, ax = plt.subplots(figsize=(8, 8))
    #     markers = ['o', 'x']  # Source는 'o', Target은 'x'로 표시
    #     for i, domain in enumerate(['Source', 'Target']):
    #         mask = all_domains == i
    #         for j, label in enumerate(np.unique(all_labels)):
    #             label_mask = all_labels[mask] == label
    #             ax.scatter(features_tsne[mask][label_mask, 0], features_tsne[mask][label_mask, 1],
    #                     color=colors[j], marker=markers[i], label=f'{domain} - Class {label}', alpha=0.8)
        
        
    #     ax.set_xlabel('t-SNE Feature 1')
    #     ax.set_ylabel('t-SNE Feature 2')
    #     ax.set_title('t-SNE Visualization of Source and Target Domains')
    #     ax.legend()
        
    #     # t-SNE 그래프 저장
    #     plt.tight_layout()
    #     plt.savefig(os.path.join(self.args.save_dir, 'domain_tsne.png'), dpi=300)
    #     plt.close()
            
    def test_tsne_all(self):
        self.model.eval()
        source_iter = iter(self.dataloaders[self.args.source_name[0]])  # Source data iterator 추가
        target_iter = iter(self.dataloaders['val'])
        
        all_features = []
        all_labels = []
        all_domains = []  # Source인지 Target인지를 구분하는 레이블 추가
        
        with torch.no_grad():
            for _ in range(len(target_iter)):
                source_data, source_labels, _ = next(source_iter)
                target_data, target_labels, _ = next(target_iter)
                
                source_data, source_labels = source_data.to(self.device), source_labels.to(self.device)
                target_data, target_labels = target_data.to(self.device), target_labels.to(self.device)
                
                _, source_features = self.model(source_data)
                _, target_features = self.model(target_data)
                
                all_features.append(source_features.cpu().numpy())
                all_features.append(target_features.cpu().numpy())
                
                all_labels.append(source_labels.cpu().numpy())
                all_labels.append(target_labels.cpu().numpy())
                
                all_domains.append(np.zeros_like(source_labels.cpu().numpy()))  # Source는 0
                all_domains.append(np.ones_like(target_labels.cpu().numpy()))   # Target은 1
        
        all_features = np.concatenate(all_features, axis=0)
        all_labels = np.concatenate(all_labels, axis=0)
        all_domains = np.concatenate(all_domains, axis=0)
        
        tsne = TSNE(n_components=3, perplexity=30, random_state=42)  # n_components를 3으로 설정
        features_tsne = tsne.fit_transform(all_features)
        
        # 시각화를 위한 색상 맵 설정
        num_classes = len(np.unique(all_labels))
        colors = plt.cm.rainbow(np.linspace(0, 1, num_classes))
        
        # Source와 Target에 대한 3D t-SNE 그래프 그리기
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='3d')  # 3D 그래프를 그리기 위한 Axes3D 사용
        markers = ['o', 'x']  # Source는 'o', Target은 'x'로 표시
        for i, domain in enumerate(['Source', 'Target']):
            mask = all_domains == i
            for j, label in enumerate(np.unique(all_labels)):
                label_mask = all_labels[mask] == label
                ax.scatter(features_tsne[mask][label_mask, 0], features_tsne[mask][label_mask, 1], features_tsne[mask][label_mask, 2],
                        color=colors[j], marker=markers[i], label=f'{domain} - Class {label}', alpha=0.8)
        
        ax.set_xlabel('t-SNE Feature 1')
        ax.set_ylabel('t-SNE Feature 2')
        ax.set_zlabel('t-SNE Feature 3')  # z축 레이블 추가
        ax.set_title('3D t-SNE Visualization of Source and Target Domains')
        ax.legend()
        filename = f'domain_tsne_3d_imba_{self.args.imba}.png'
        # 3D t-SNE 그래프 저장
        plt.tight_layout()
        plt.savefig(os.path.join(self.args.save_dir, filename), dpi=300)
        plt.close()
            