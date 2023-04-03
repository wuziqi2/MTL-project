import torch
from torch import nn
from torch.utils.data import DataLoader

from evaluator import R2_SCORE

# > The class `LR` defines a linear regression model with weights `self.W` and bias `self.b`
class LR(nn.Module):

    def __init__(self, n_features, n_tasks):
        super(LR, self).__init__()

        # define parameters
        self.linear = nn.Linear(n_features, n_tasks, bias=True)

        self.loss_fn = nn.MSELoss(reduction='mean')

        # define evaluator
        self.evaluators = [R2_SCORE()]

    def forward(self, x):
        """
        > The function `forward` takes in an input `x` and returns a prediction `preds` based on the weights
        `self.W` and bias `self.b`
        
        :param x: the input data
        :return: The prediction of the model.
        """
        out = self.linear(x)
        return out
    
    def compute_loss(self, y_pred, y):
        # l2_norm = torch.norm(y - y_pred) #l2 norm
        # loss = torch.pow(l2_norm, 2) #sum of l2 norm
        # return loss
        loss = self.loss_fn(y_pred, y)
        return loss
    
    def eval(self, test_data:DataLoader, device) -> dict:
        with torch.no_grad():
            test_loss = 0
            metrics_vals = {type(k).__name__:torch.zeros(3).to(device) for k in self.evaluators}

            for x, y in test_data:
                x = x.to(device)
                y = y.to(device)
                pred = self.forward(x)

                test_loss = self.compute_loss(pred, y)

                for e in self.evaluators:
                    metrics_vals[type(e).__name__] += e.compute(y, pred) #[1, task]

            return test_loss, metrics_vals