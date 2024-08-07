import argparse

def parse_args():
    parser = argparse.ArgumentParser(description='From github.com/Feaxure-fresh/TL-Bearing-Fault-Diagnosis')
 

    # basic parameters
    parser.add_argument('--imba', type=bool, default=False, help='Sample imbalance setting')# str
    parser.add_argument('--model_name', type=str, default='DANN',
                        help='Name of the model (in ./models directory)')
    parser.add_argument('--Domain', type=str, default='exp')
    parser.add_argument('--source', type=str, default='JNU_0',
                        help='Source data, separated by "," (select specific conditions of the dataset with name_number, such as CWRU_0)')
    parser.add_argument('--target', type=str, default='JNU_1',
                        help='Target data (select specific conditions of the dataset with name_number, such as CWRU_0)')
    parser.add_argument('--data_dir', type=str, default="/content/UDA_Bearing_Fault_Diagnosis/datasets",
                        help='Directory of the datasets')
    parser.add_argument('--train_mode', type=str, default='single_source',
                        choices=['single_source', 'source_combine', 'multi_source'],
                        help='Training mode (select correctly before training)')
    parser.add_argument('--cuda_device', type=str, default='0',
                        help='Allocate the device to use only one GPU ('' means using cpu)')
    parser.add_argument('--save_dir', type=str, default='./ckpt',
                        help='Directory to save logs and model checkpoints')
    parser.add_argument('--max_epoch', type=int, default=10,
                        help='Number of epochs')
    parser.add_argument('--batch_size', type=int, default=32,
                        help='Batch size')
    parser.add_argument('--num_workers', type=int, default=0,
                        help='Number of workers for dataloader')
    parser.add_argument('--signal_size', type=int, default=2048,
                        help='Signal length split by sliding window')
    parser.add_argument('--random_state', type=int, default=128,
                        help='Random state for the entire training')

    # optimization information
    parser.add_argument('--normlizetype', type=str, choices=['0-1', '-1-1', 'mean-std','None'], default='mean-std',
                        help='Data normalization methods')
    parser.add_argument('--opt', type=str, choices=['sgd', 'adam'], default='adam', help='Optimizer')
    parser.add_argument('--lr', type=float, default=1e-3, help='Initial learning rate')
    parser.add_argument('--momentum', type=float, default=0.9, help='Momentum for sgd')
    parser.add_argument('--betas', type=tuple, default=(0.9, 0.999), help='Betas for adam')
    parser.add_argument('--weight_decay', type=float, default=1e-3, help='Weight decay for both sgd and adam')
    parser.add_argument('--lr_scheduler', type=str, choices=['step', 'exp', 'stepLR', 'fix'], default='stepLR',
                        help='Type of learning rate schedule')
    parser.add_argument('--gamma', type=float, default=0.2,
                        help='Parameter for the learning rate scheduler (except "fix")')
    parser.add_argument('--steps', type=str, default='20',
                        help='Step of learning rate decay for "step" and "stepLR"')
    parser.add_argument('--tradeoff', type=list, default=['exp', 'exp', 'exp'],
                        help='Trade-off coefficients for the sum of losses, integer or "exp" ("exp" represents an increase from 0 to 1)')
    parser.add_argument('--dropout', type=float, default=0.2, help='Dropout layer coefficient')
    
    # save and load
    parser.add_argument('--save', type=bool, default=True, help='Save logs and trained model checkpoints')
    parser.add_argument('--load_path', type=str, default='',
                        help='Load trained model checkpoints from this path (for testing, not for resuming training)')
    parser.add_argument('--tsne', type=bool, default=False, help='tsne and confusion matrix plot')
    
    
    
    args = parser.parse_args()
    return args
    
