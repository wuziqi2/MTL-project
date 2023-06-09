#python single_LR.py --device=cuda --batch=1024 --lr=5e-4 --optim=Adam --epoch=100 --comment=log
from dataset import PostData, ToTensor, Log, random_split
from models import SLR

import torch
torch.manual_seed(666)
from torch.utils.data import DataLoader
import argparse
import logging
from tqdm import tqdm, trange
import time
import atexit
import numpy as np
import re

#Parsing the arguments that are passed in the command line.
parser = argparse.ArgumentParser()
# parser.add_argument('--model', choices=['LR', 'LLR'], help="MTL model", required=True)
# parser.add_argument('--onehot', action='store_true', help="if data use onehot encoding", required=False)
parser.add_argument('--device', type=str, default='cpu', help="hardware to perform training", required=False)
parser.add_argument('--mode', choices=['train', 'test'], default='train', help="train model or test model", required=False)
parser.add_argument('--model_path', type=str, default=None, help="trained model path", required=False)
parser.add_argument('--batch', type=int, default=64, help="batch size for feeding data", required=False)
parser.add_argument('--lr', type=float, default=1e-3, help="learning rate for training model", required=False)
parser.add_argument('--optim', choices=['SGD', 'Adam'], default="Adam", help="optimizer for training model", required=False)
parser.add_argument('--epoch', type=int, default=100, help="epoch number for training model", required=False)
parser.add_argument('--comment', type=str, help="additional comment for model", required=False)
args = parser.parse_args()

print("="*20 + "START PROGRAM" + "="*20)

#1. Check device
if re.compile('(cuda|cuda:\d+)').match(args.device) and torch.cuda.is_available():
    device = torch.device(args.device)
elif args.device == 'mps' and torch.backends.mps.is_available(): # type: ignore
    device = torch.device('mps')
else:
    device = torch.device('cpu')
print(f"Computing device: {device}")

#2. Load data
x_trans_list = [ToTensor()]
y_trasn_list = [ToTensor(), Log()]
data = PostData(onehot_cols=['sentiment'], tar_cols=['Item_Views', 'Item_Likes', 'Item_Comments'], \
                x_transforms=x_trans_list, y_transforms=y_trasn_list)
train_data, valid_data, test_data = random_split(data, [0.8,0.1,0.1]) #train:test = 8:2

train_dataloader = DataLoader(train_data, batch_size=args.batch, shuffle=True)
valid_dataloader = DataLoader(valid_data, batch_size=len(valid_data), shuffle=True)
test_dataloader = DataLoader(test_data, batch_size=len(test_data), shuffle=True)
print(f"Data loaded. Training data: {len(train_data)}; Valid data: {len(valid_data)}; Testing data: {len(test_data)}")


#3. Select model
model0 = SLR(data.get_feature_num(), 0).to(device)
model1 = SLR(data.get_feature_num(), 1).to(device)
model2 = SLR(data.get_feature_num(), 2).to(device)

# save model before exit
def exit_handler():
    MODEL_PATH = (f"./models/model0_{args.batch}_{args.lr}_{args.optim}_{args.comment}.pt")
    torch.save(model0.state_dict(), MODEL_PATH)
    MODEL_PATH = (f"./models/model1_{args.batch}_{args.lr}_{args.optim}_{args.comment}.pt")
    torch.save(model1.state_dict(), MODEL_PATH)
    MODEL_PATH = (f"./models/model2_{args.batch}_{args.lr}_{args.optim}_{args.comment}.pt")
    torch.save(model2.state_dict(), MODEL_PATH)
atexit.register(exit_handler)


for i, model in enumerate([model0, model1, model2]):
    #Configure logging
    LOG_PATH = (f"./logs/model{i}_{args.batch}_{args.lr}_{args.optim}_{args.comment}.log")
    logging.basicConfig(filename=LOG_PATH, filemode='w', level=logging.DEBUG, format='%(levelname)s - %(message)s')

    if args.optim=='SGD':
        optimizer = torch.optim.SGD(model.parameters(), lr=args.lr)
    else: # default adam
        optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    ### Test Mode
    if args.mode=="test":
        print("-"*10 + "Start evaluating " + "-"*10)
        time_s = time.time()
        
        test_loss, metrics = model.eval(test_dataloader, device)

        # print result
        print(f"AVG TEST LOSS: {test_loss/len(test_dataloader)}")
        for e, val in metrics.items():
            print(f"AVG SCORE for {e}: {val}")
        
        print(f"evalution time {time.time()-time_s}s")
        print("="*10 + "END PROGRAM" + "="*10)

    ### Train Mode
    else: 
        print("-"*10 + "Start training " + "-"*10)

        # paramters for early stop
        best_loss = np.inf
        min_delta=0.001
        counter = 0
        patience = 10
        stop_training = False

        t_epoch = trange(args.epoch, leave=False)
        epoch_loss = 0
        for epoch in t_epoch:
            logging.debug(f"EPOCH {epoch}\n")
            t_epoch.set_description(f"Epoch {epoch} - avg loss: {epoch_loss/len(train_dataloader)}")
            t_epoch.refresh()
            epoch_loss = 0 #reset epoch loss for current epoch training
            
            t_batch = tqdm(train_dataloader, leave=False)
            batch_loss = 0
            for batch, (x, y) in enumerate(t_batch):
                # print(x[10])
                if batch%10 == 0:
                    t_batch.set_description(f"Batch {batch} - avg loss {batch_loss}")
                    t_batch.refresh()
                    # logging.info(f"Batch {batch} - avg loss {batch_loss}\n")

                #load data to device
                x = x.to(device)
                y = y.to(device)
                pred = model(x)
                # print(x.shape,y.shape, pred.shape) [256, 9] [256, 3] [256, 3]
                # print(y.shape, pred.shape)
                # break
                
                batch_loss = model.compute_loss(pred, y)
                epoch_loss += batch_loss
                

                # backpropagation
                optimizer.zero_grad()
                batch_loss.backward()
                optimizer.step()
                # torch.nn.utils.clip_grad_norm(parameters=model.parameters(), max_norm=10, norm_type=2.0)

                time.sleep(0.01)

            # eavluate on test data
            train_loss = epoch_loss/len(train_dataloader)
            valid_loss, metrics = model.eval(valid_dataloader, device)
            logging.debug(f"train loss: {train_loss}\n")
            logging.debug(f"valid loss: {valid_loss/len(valid_dataloader)}\n")
            logging.debug(f"metrics performance: {metrics}\n")
            logging.debug('-'*10+'\n')

            # early stop
            # Check for early stopping
            if valid_loss < best_loss - min_delta:
                best_loss = valid_loss
                counter = 0
            else:
                counter += 1
                if counter >= patience:
                    logging.debug("Early stopping: validation loss did not improve for {} epochs".format(patience))
                    stop_training = True
                    break
        
        print("="*10 + "END PROGRAM" + "="*10)
    
    
    









