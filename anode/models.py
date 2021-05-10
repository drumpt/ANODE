import torch
import torch.nn as nn
from math import pi
from torchdiffeq import odeint, odeint_adjoint


MAX_NUM_STEPS = 1000  # Maximum number of steps for ODE solver


class ODEFunc(nn.Module):
    """MLP modeling the derivative of ODE system.

    Parameters
    ----------
    device : torch.device

    data_dim : int
        Dimension of data.

    hidden_dim : int
        Dimension of hidden layers.

    augment_dim: int
        Dimension of augmentation. If 0 does not augment ODE, otherwise augments
        it with augment_dim dimensions.

    time_dependent : bool
        If True adds time as input, making ODE time dependent.

    non_linearity : string
        One of 'relu' and 'softplus'
    """
    def __init__(self, device, data_dim, hidden_dim, augment_dim=0,
                 time_dependent=False, non_linearity='relu'):
        super(ODEFunc, self).__init__()
        self.device = device
        self.augment_dim = augment_dim
        self.data_dim = data_dim
        self.input_dim = data_dim + augment_dim
        self.hidden_dim = hidden_dim
        self.nfe = 0  # Number of function evaluations
        self.time_dependent = time_dependent

        if time_dependent:
            self.fc1 = nn.Linear(self.input_dim + 1, hidden_dim)
        else:
            self.fc1 = nn.Linear(self.input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, self.input_dim)

        if non_linearity == 'relu':
            self.non_linearity = nn.ReLU()
        elif non_linearity == 'softplus':
            self.non_linearity = nn.Softplus()

    def forward(self, t, x):
        """
        Parameters
        ----------
        t : torch.Tensor
            Current time. Shape (1,).

        x : torch.Tensor
            Shape (batch_size, input_dim)
        """
        # Forward pass of model corresponds to one function evaluation, so
        # increment counter
        self.nfe += 1
        if self.time_dependent:
            # Shape (batch_size, 1)
            t_vec = torch.ones(x.shape[0], 1).to(self.device) * t
            # Shape (batch_size, data_dim + 1)
            t_and_x = torch.cat([t_vec, x], 1)
            # Shape (batch_size, hidden_dim)
            out = self.fc1(t_and_x)
        else:
            out = self.fc1(x)
        out = self.non_linearity(out)
        out = self.fc2(out)
        out = self.non_linearity(out)
        out = self.fc3(out)
        return out


class ODEBlock(nn.Module):
    """Solves ODE defined by odefunc.

    Parameters
    ----------
    device : torch.device

    odefunc : ODEFunc instance or anode.conv_models.ConvODEFunc instance
        Function defining dynamics of system.

    is_conv : bool
        If True, treats odefunc as a convolutional model.

    tol : float
        Error tolerance.

    adjoint : bool
        If True calculates gradient with adjoint method, otherwise
        backpropagates directly through operations of ODE solver.
    """
    def __init__(self, device, odefunc, is_conv=False, tol=1e-3, adjoint=False):
        super(ODEBlock, self).__init__()
        # Task 1.
        # TODO : implement this
        self.device = device
        self.odefunc = odefunc
        self.is_conv = is_conv
        self.tol = tol
        self.adjoint = adjoint

    def forward(self, x, eval_times=None):
        # Task 1. 
        # TODO : implement this
        integration_time = torch.tensor([0, 1]).float() if eval_times == None else torch.tensor(eval_times).float()

        if self.odefunc.augment_dim > 0 and self.is_conv:
            b, c, h, w = x.shape
            aug = torch.zeros(b, self.odefunc.augment_dim, h, w).to(self.device)
            x = torch.cat([x, aug], 1).to(self.device)
        elif self.odefunc.augment_dim > 0 and not self.is_conv:
            b, d = x.shape
            aug = torch.zeros(b, self.odefunc.augment_dim).to(self.device)
            x = torch.cat([x, aug], 1).to(self.device)
        
        if self.adjoint:
            out = odeint_adjoint(self.odefunc.to(self.device), x.to(self.device), integration_time.to(self.device), rtol = self.tol, atol = self.tol, method = "dopri5", options = {'max_num_steps' : MAX_NUM_STEPS})
        else:
            out = odeint(self.odefunc.to(self.device), x.to(self.device), integration_time.to(self.device), rtol = self.tol, atol = self.tol, method = "dopri5", options = {'max_num_steps' : MAX_NUM_STEPS})

        if eval_times == None:
            return out[1] # t = 1
        else:
            return out

    def trajectory(self, x, timesteps):
        """Returns ODE trajectory.

        Parameters
        ----------
        x : torch.Tensor
            Shape (batch_size, self.odefunc.data_dim)

        timesteps : int
            Number of timesteps in trajectory.
        """
        integration_time = torch.linspace(0., 1., timesteps)
        return self.forward(x, eval_times=integration_time)


class ODENet(nn.Module):
    """An ODEBlock followed by a Linear layer.

    Parameters
    ----------
    device : torch.device

    data_dim : int
        Dimension of data.

    hidden_dim : int
        Dimension of hidden layers.

    output_dim : int
        Dimension of output after hidden layer. Should be 1 for regression or
        num_classes for classification.

    augment_dim: int
        Dimension of augmentation. If 0 does not augment ODE, otherwise augments
        it with augment_dim dimensions.

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
    def __init__(self, device, data_dim, hidden_dim, output_dim=1,
                 augment_dim=0, time_dependent=False, non_linearity='relu',
                 tol=1e-3, adjoint=False):
        super(ODENet, self).__init__()
        self.device = device
        self.data_dim = data_dim
        self.hidden_dim = hidden_dim
        self.augment_dim = augment_dim
        self.output_dim = output_dim
        self.time_dependent = time_dependent
        self.tol = tol

        odefunc = ODEFunc(device, data_dim, hidden_dim, augment_dim,
                          time_dependent, non_linearity)

        self.odeblock = ODEBlock(device, odefunc, tol=tol, adjoint=adjoint)
        self.linear_layer = nn.Linear(self.odeblock.odefunc.input_dim,
                                      self.output_dim)

    def forward(self, x, return_features=False):
        features = self.odeblock(x)
        pred = self.linear_layer(features)
        if return_features:
            return features, pred
        return pred
