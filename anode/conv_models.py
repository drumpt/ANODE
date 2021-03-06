import torch
import torch.nn as nn
from anode.models import ODEBlock
from torchdiffeq import odeint, odeint_adjoint

device = "cuda:0" if torch.cuda.is_available() else 'cpu'

class Conv2dTime(nn.Conv2d):
    """
    Implements time dependent 2d convolutions, by appending the time variable as
    an extra channel.
    """
    def __init__(self, in_channels, *args, **kwargs):
        super(Conv2dTime, self).__init__(in_channels + 1, *args, **kwargs)

    def forward(self, t, x):
        # Task2
        # TODO : implement this
        b, c, h, w = x.shape
        aug = torch.ones((b, 1, h, w)).to(device) * t
        out = torch.cat([aug, x], 1)
        return super(Conv2dTime, self).forward(out)

class ConvODEFunc(nn.Module):
    """Convolutional block modeling the derivative of ODE system.

    Parameters
    ----------
    device : torch.device

    img_size : tuple of ints
        Tuple of (channels, height, width).

    num_filters : int
        Number of convolutional filters.

    augment_dim: int
        Number of augmentation channels to add. If 0 does not augment ODE.

    time_dependent : bool
        If True adds time as input, making ODE time dependent.

    non_linearity : string
        One of 'relu' and 'softplus'
    """
    def __init__(self, device, img_size, num_filters, augment_dim=0,
                 time_dependent=False, non_linearity='relu'):
        super(ConvODEFunc, self).__init__()
        # Task 2. 
        # TODO : implement this
        self.device = device
        self.img_size  = img_size
        self.num_filters = num_filters
        self.augment_dim = augment_dim
        self.time_dependent = time_dependent
        self.nfe = 0

        if time_dependent:
            self.cv1 = Conv2dTime(in_channels = self.img_size[0] + self.augment_dim,
                                  out_channels = self.num_filters,
                                  kernel_size = 1).to(device)
            self.cv2 = Conv2dTime(in_channels = self.num_filters,
                                  out_channels = self.num_filters,
                                  kernel_size = 3, padding = 1).to(device)
            self.cv3 = Conv2dTime(in_channels = self.num_filters,
                                  out_channels = self.img_size[0] + self.augment_dim,
                                  kernel_size = 1).to(device)
        else:
            self.cv1 = nn.Conv2d(in_channels = self.img_size[0] + self.augment_dim,
                                 out_channels = self.num_filters,
                                 kernel_size = 1).to(device)
            self.cv2 = nn.Conv2d(in_channels = self.num_filters,
                                 out_channels = self.num_filters,
                                 kernel_size = 3, padding = 1).to(device)
            self.cv3 = nn.Conv2d(in_channels = self.num_filters,
                                 out_channels = self.img_size[0] + self.augment_dim,
                                 kernel_size = 1).to(device)

        if non_linearity == 'relu':
            self.non_linearity = nn.ReLU().to(device)
        elif non_linearity == 'softplus':
            self.non_linearity = nn.Softplus().to(device)

    def forward(self, t, x):
        """
        Parameters
        ----------
        t : torch.Tensor
            Current time.

        x : torch.Tensor
            Shape (batch_size, input_dim)
        """
        # Task 2. 
        # TODO : implement this
        self.nfe += 1
        if self.time_dependent:
            out = self.cv1(t.to(self.device), x.to(self.device))
            out = self.non_linearity(out)
            out = self.cv2(t.to(self.device), out)
            out = self.non_linearity(out)
            out = self.cv3(t.to(self.device), out)
        else:
            out = self.cv1(x.to(self.device))
            out = self.non_linearity(out)
            out = self.cv2(out)
            out = self.non_linearity(out)
            out = self.cv3(out)
        return out

class ConvODENet(nn.Module):
    """Creates an ODEBlock with a convolutional ODEFunc followed by a Linear
    layer.

    Parameters
    ----------
    device : torch.device

    img_size : tuple of ints
        Tuple of (channels, height, width).

    num_filters : int
        Number of convolutional filters.

    output_dim : int
        Dimension of output after hidden layer. Should be 1 for regression or
        num_classes for classification.

    augment_dim: int
        Number of augmentation channels to add. If 0 does not augment ODE.

    time_dependent : bool
        If True adds time as input, making ODE time dependent.

    non_linearity : string
        One of 'relu' and 'softplus'

    tol : float
        Error tolerance.

    adjoint : bool
        If True calculates gradient with adjoint method, otherwise
        backpropagates directly through operations of ODE solver.
    """
    def __init__(self, device, img_size, num_filters, output_dim=1,
                 augment_dim=0, time_dependent=False, non_linearity='relu',
                 tol=1e-3, adjoint=False):
        super(ConvODENet, self).__init__()
        self.device = device
        self.img_size = img_size
        self.num_filters = num_filters
        self.augment_dim = augment_dim
        self.output_dim = output_dim
        self.flattened_dim = (img_size[0] + augment_dim) * img_size[1] * img_size[2]
        self.time_dependent = time_dependent
        self.tol = tol

        odefunc = ConvODEFunc(device, img_size, num_filters, augment_dim,
                              time_dependent, non_linearity).to(device)

        self.odeblock = ODEBlock(device, odefunc, is_conv=True, tol=tol,
                                 adjoint=adjoint).to(device)

        self.linear_layer = nn.Linear(self.flattened_dim, self.output_dim).to(device)

    def forward(self, x, return_features=False):
        features = self.odeblock(x)
        pred = self.linear_layer(features.view(features.size(0), -1))
        if return_features:
            return features, pred
        return pred
