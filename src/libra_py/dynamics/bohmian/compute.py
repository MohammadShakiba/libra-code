# *********************************************************************************
# * Copyright (C) 2025 Alexey V. Akimov
# *
# * This file is distributed under the terms of the GNU General Public License
# * as published by the Free Software Foundation, either version 3 of
# * the License, or (at your option) any later version.
# * See the file LICENSE in the root directory of this distribution
# * or <http://www.gnu.org/licenses/>.
# ***********************************************************************************
"""
.. module:: compute
   :platform: Unix
   :synopsis: This module implements functions for Bohmian dynamics
       List of functions:
         * rho_gaussian(q, Q, sigma)
         * rho_lorentzian(q, Q, sigma)
         * quantum_potential(Q, sigma, mass, TBF)
         * compute_derivatives(q, function, function_params)
         * compute_derivatives_hess(q, function, function_params)
         * init_variables(ntraj, opt)
         * md( q, p, mass_mat, params )

.. moduleauthor:: Alexey V. Akimov

"""

__author__ = "Alexey V. Akimov"
__copyright__ = "Copyright 2025 Alexey V. Akimov"
__credits__ = ["Alexey V. Akimov"]
__license__ = "GNU-3"
__version__ = "1.0"
__maintainer__ = "Alexey V. Akimov"
__email__ = "alexvakimov@gmail.com"
__url__ = "https://github.com/Quantum-Dynamics-Hub/libra-code"

import torch
import numpy as np

def rho_gaussian(q, Q, sigma):
    """
    Args: 
    * q (Tensor(ndof) ) - coordinate of the current point of interest
    * Q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * sigma (Tensor(ntraj, ndof)) - width parameter for each trajectory

    Returns:
    Tensor(1) - probability density at the point of interest

    """
    _SQRT_2PI = torch.sqrt(torch.tensor(2.0 * torch.pi))

    ntraj, ndof = Q.shape[0], Q.shape[1]
    return torch.sum( (1.0/ntraj) * torch.prod(  torch.exp( - 0.5*(q-Q)**2/sigma**2 )/(sigma * _SQRT_2PI ),   1,  False) ) 


def rho_lorentzian(q, Q, sigma):
    """
    Args:
    * q (Tensor(ndof) ) - coordinate of the current point of interest
    * Q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * sigma (Tensor(ntraj, ndof)) - width parameter for each trajectory

    Returns:
    Tensor(1) - probability density at the point of interest
    """
    ntraj, ndof = Q.shape[0], Q.shape[1]
    y =  torch.sum( (1.0/ntraj) * torch.prod( (1.0/torch.pi) * sigma/( (q-Q)**2 + sigma**2 ),   1,  False) )
    return y


def quantum_potential_orginal(Q, sigma, mass, TBF):
    """
    Args:
    * Q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * sigma (Tensor(ndof)) - width parameters for each trajectory
    * mass ( Tensor(1, ndof)) - masses of all DOFs, same for all trajectories
    * TBF (object) - basis function reference (`rho_gaussian` or `rho_lorentzian`)

    Returns:
    Tensor(1) - quantum potential summed over all trajectory points
    """

    ntraj, ndof = Q.shape[0], Q.shape[1]
    U = torch.zeros( (1,), requires_grad=True)
    for k in range(ntraj):
        f = TBF(Q[k], Q, sigma);
        [deriv1] = torch.autograd.grad(f, [Q], create_graph=True, retain_graph=True);
        for i in range(ndof):
            [deriv2] = torch.autograd.grad(deriv1[k,i], [Q], create_graph=True, retain_graph=True);
            u = -(0.25/mass[0,i])*( deriv2[k, i]/f  - 0.5 * (deriv1[k,i]/f)**2 );
            U = U + u
    return U


def quantum_potential(Q, sigma, mass, TBF):
    """
    Compute quantum potential in a fully vectorized way.

    Args:
        Q (Tensor): shape (ntraj, ndof), requires_grad=True
        sigma (Tensor): shape (ntraj, ndof) or (ndof,)
        mass (Tensor): shape (1, ndof)
        TBF (callable): basis function (e.g., rho_gaussian or rho_lorentzian)

    Returns:
        Tensor(1,) — scalar total quantum potential
    """
    ntraj, ndof = Q.shape

    # Compute rho for each trajectory point: shape (ntraj,)
    f_list = torch.stack([TBF(Q[k], Q, sigma) for k in range(ntraj)], dim=0)  # shape: (ntraj,)
    
    # Ensure Q requires grad
    Q.requires_grad_(True)

    # Compute first derivative: shape (ntraj, ndof)
    grad_f = torch.autograd.grad(f_list.sum(), Q, create_graph=True)[0]  # shape: (ntraj, ndof)

    # Compute second derivatives (Hessian diagonal elements)
    deriv2 = torch.zeros_like(Q)
    for i in range(ndof):
        grad_i = torch.autograd.grad(grad_f[:, i].sum(), Q, create_graph=True)[0]  # shape: (ntraj, ndof)
        deriv2[:, i] = grad_i[:, i]  # extract diagonal part only

    # Expand mass to match shape (ntraj, ndof)
    mass_exp = mass.expand(ntraj, -1)

    # Compute quantum potential batch-wise
    term1 = deriv2 / f_list.unsqueeze(1)
    term2 = 0.5 * (grad_f / f_list.unsqueeze(1)) ** 2
    U = -0.25 / mass_exp * (term1 - term2)  # shape: (ntraj, ndof)

    # Sum over trajectories and DOFs
    U_total = U.sum()

    return U_total





def compute_derivatives(q, function, function_params):
    """
    Args:
    * q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * function (object) - reference to PyTorch function that computes energy
          the functions should be called as `function(q function_params)`
    * function_params (dict) - parameters of the model Hamiltonian

    Returns:
    * f (Tensor(0)) - energy
    * grad (Tensor(ntraj, ndof)) - gradients of the Hamiltonian with respect to
          all DOFs of all trajectories
    """
    
    ntraj, ndof = q.shape[0], q.shape[1]

    # Compute the function itself
    f = function(q, function_params)

    # Compute the first gradients
    [grad] = torch.autograd.grad(f, q, create_graph=False, retain_graph=False)

    return f, grad


def compute_derivatives_hess(q, function, function_params):
    """
    Args: 
    * q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * function (object) - reference to PyTorch function that computes energy
             the functions should be called as `function(q function_params)`
    * function_params (dict) - parameters of the model Hamiltonian

    Returns:
    * f (Tensor(0)) - energy
    * grad (Tensor(ntraj, ndof)) - gradients of the Hamiltonian with respect to
          all DOFs of all trajectories
    * hess (Tensor(ntraj, ndof, ndof)) - Hessians of the Hamiltonian for all DOFs
     for all trajectories, but not cross-trajectory
    
    Note: Hessian calculations may be quite expensive
    """
    ntraj, ndof = q.shape[0], q.shape[1]

    # Compute the function itself
    f = function(q, function_params)

    # Compute the first gradients
    [grad] = torch.autograd.grad(f, q, create_graph=True, retain_graph=True)

    # Compute the second gradients
    hess = torch.zeros( (ntraj, ndof, ndof) )
    for k in range(ntraj):
        for i in range(ndof):
            [ d2f ] = torch.autograd.grad( grad[k, i], q, create_graph=False, retain_graph=False)
            hess[k, i, :] = d2f[k, :]

    return f, grad, hess


def init_variables(ntraj, opt):
    """
    So far, this is only good for very specific cases - the models
    from Wang-Martens-Zheng paper:

    Wang, L.; Martens, C. C.; Zheng, Y. Entangled Trajectory Molecular Dynamics in Multidimensional Systems: 
    Two-Dimensional Quantum Tunneling through the Eckart Barrier. J. Chem. Phys. 2012, 137 (3), 034113. 
    https://doi.org/10.1063/1.4736559.   


    Args:
    * ntraj (int) - the number of trajectories
    * opt (int) - the type of initial condition
          opt: 1 - q = (-1, 0), p = (3.0, 0.0)
          opt: 2 - q = (-1, 0), p = (4.0, 0.0)

    """

    mass = 2000.0
    omega = 0.004
    
    sigma_q = np.sqrt(0.5/(mass*omega))
    sigma_p = np.sqrt(0.5*mass*omega)
            
    q_mean = torch.tensor([[-1.0, 0.0]]*ntraj)
    q_std = torch.tensor([[ sigma_q, sigma_q]]*ntraj)
    q = torch.normal(q_mean, q_std)

    p_mean = torch.tensor([[ 3.0 , 0.0]]*ntraj)
    if opt == 2:
        p_mean = torch.tensor([[ 4.0 , 0.0]]*ntraj)
    p_std = torch.tensor([[ sigma_p, sigma_p]]*ntraj)
    p = torch.normal(p_mean, p_std)

    q.requires_grad_(True)
    p.requires_grad_(True)

    masses = torch.tensor([[mass, mass]])

    return q, p, masses 



def md( q, p, mass_mat, params ):
    """
    Args:
    * q (Tensor(ntraj, ndof)) - coordinates of all trajectories
    * p (Tensor(ntraj, ndof)) - momenta of all trajectories
    * mass_mat (Tensor(1, ndof)) - masses for all DOFs (same for all trajectories)
    * params:
      - nsteps (int) - how many steps to do
      - dt (float) - integration timestep [in a.u.]
      - do_bohmian (int or Bool) - whether to include quantum potential: 0 - no, 1 - yes
      - prefix (string) - the name of the ".pt" file where all will be saved
      - ham (object) - function that defined Hamiltonian - should be called as `ham(q, ham_params)`
      - ham_params (dict) - parameters of the model Hamiltonian
      - qpot_sigmas ( Tensor(ndof)) - width paramters of the TBFs 
      - tbf_type (object) - function that defines the type of trajectory basis functions used in computing
           probability density. Can be either: `rho_gaussian` or `rho_lorentzian` defined in this module
           If no quantum potential is used, define it as `None`

    Returns:
    None, but saves the key variable in a ".pt" file
    """
    
    nsteps = params["nsteps"]
    dt = params["dt"]
    do_bohmian = params["do_bohmian"]
    ntraj = q.shape[0]
    ndof = q.shape[1]
    prefix = params["prefix"]
    ham = params["ham"]
    ham_params = params["ham_params"]
    sigma = params["qpot_sigmas"]
    tbf_type = params["tbf_type"]
    print_period = params["print_period"]

    q_traj = torch.zeros( nsteps, ntraj, ndof )
    p_traj = torch.zeros( nsteps, ntraj, ndof )
    t = torch.zeros(nsteps)
    P = torch.zeros(nsteps)
    E = torch.zeros(nsteps, 4 )  # kin, pot, quantum, tot

    print("Starting MD")
    E_pot, grad = compute_derivatives(q, ham, ham_params)
    f = -grad 
    if do_bohmian:
        q_pot = quantum_potential(q, sigma, mass_mat, tbf_type)
        E[0,2] = q_pot.detach()/ntraj
        [q_force] = torch.autograd.grad( q_pot, [q], create_graph=False, retain_graph=False)
        f = f - q_force

    E[0,0] = torch.sum( 0.5 * p**2/ mass_mat)/ntraj
    E[0,1] = E_pot.detach()/ntraj
    E[0,3] = E[0,0] + E[0,1] + E[0,2]    
    P[0] = 0.0
    t[0] = 0.0

    #q = q.detach().clone().requires_grad_(True)
    q_traj[0,:,:] = q.detach()
    p_traj[0,:,:] = p.detach()

    for i in range(1,nsteps):
        q = q.detach().clone().requires_grad_(True)
        p = p.detach().clone().requires_grad_(False)

        p = p + 0.5 * f * dt
        q = q + dt * p/mass_mat

        E_pot, grad = compute_derivatives(q, ham, ham_params)
        f = -grad 
        if do_bohmian:
            q_pot = quantum_potential(q, sigma, mass_mat, tbf_type)
            E[i,2] = q_pot.detach()/ntraj
            [q_force] = torch.autograd.grad( q_pot, [q], create_graph=False, retain_graph=False)
            f = f - q_force    
            
        p = p + 0.5 * f * dt

        E[i,0] = torch.sum( 0.5 * p**2/ mass_mat)/ntraj
        E[i,1] = E_pot.detach()/ntraj
        E[i,3] = E[i,0] + E[i,1] + E[i,2]
        t[i] = i * dt
        q_traj[i,:,:] = q.detach()
        p_traj[i,:,:] = p.detach()
    
        # Compute the transmission probability
        a = q[:,0].detach()  # x-component only
        P[i] = a.masked_fill(a>0, 1).masked_fill(a<0, 0).sum()/ntraj # we sum up the elements that are larger than 0.0

        if i%print_period==0:
            print(t[i].item(), E[i])

    #return t, q_traj, p_traj, E, P
    torch.save( {"t":t, "q_traj":q_traj, "p_traj":p_traj, "E":E, "P":P }, F"{prefix}.pt" )



