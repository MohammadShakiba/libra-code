#*********************************************************************************
#* Copyright (C) 2018-2019 Alexey V. Akimov
#*
#* This file is distributed under the terms of the GNU General Public License
#* as published by the Free Software Foundation, either version 2 of
#* the License, or (at your option) any later version.
#* See the file LICENSE in the root directory of this distribution
#* or <http://www.gnu.org/licenses/>.
#*
#*********************************************************************************/
"""
.. module:: pdos
   :platform: Unix, Windows
   :synopsis: 
       This module implements functions for computing Projected (Partial) 
       Densities of States (pDOS) from various outputs

.. moduleauthor:: Alexey V. Akimov

"""

import math
import os
import sys
import time
if sys.platform=="cygwin":
    from cyglibra_core import *
elif sys.platform=="linux" or sys.platform=="linux2":
    from liblibra_core import *
from . import units
import util.libutil as comn
import numpy as np

def convolve(X0, Y0, dx0, dx, var):
    """
    This function convolves the original data with the Gaussian
    of a given width:  exp(- (x - x0)^2 / (2*var^2) )
    This also means the energy grid spacing may change (usually to a denser one)
    The difference in grid densities is defined by the multiplicative factor dx0/dx

    Args:
        X0 ( MATRIX(N0, 1) ): original X grid, N0 - the number of energy grid points
        Y0 ( MATRIX(N0, Nproj) ): original Y grids, Nproj - the number of projections
            to consider
        dx0 ( double ): original X grid spacing [in units of energy]
        dx ( double ): new X grid spacing [in units of energy]
        var ( double ): width of the Gaussians that broaden the original data [in units of energy]

    Returns:
        tuple: ( X, Y ), where:

            * X ( MATRIX(N, 1) ): new X grid, N - the new number of energy grid points (N*dx = N0*dx0)
            * Y ( MATRIX(N, Nproj) ): new Y grids, Nproj has the same meaning as in Y0

    """

    mult = int(dx0/dx)     # making grid mult times bigger
    print("multiplication factor is = ", mult)
    print("original grid spacing = ", dx0)
    print("new grid spacing = ", dx)
    print("gaussian variance = ", var)
        
    # Prepare arrays
    N0    = Y0.num_of_rows     # how many original grid points
    nproj = Y0.num_of_cols     # how many components
    N  = N0*mult               # how many new grid points

    X = MATRIX(N, 1)           # new X axis
    Y = MATRIX(N, nproj)       # new Y axes


    for i in range(0,N):
        X.set(i,0, X0.get(0,0) + i*dx)


    area = var*math.sqrt(2.0*math.pi)  # area under Gaussian of type exp( -(x - x0)^2 / 2*var^2 ) 
    alp = 0.5/(var**2)

    for j in range(0,nproj):  

        for i0 in range(0,N0):   # all initial grid points
            x0 = X0.get(i0, 0)
            y0 = Y0.get(i0, j)

            area0 = dx0*y0      # initial area
            w = area0/area

            for i in range(0,N):
                x = X.get(i, 0)
                Y.add(i,j, w*math.exp(-alp*(x0-x)**2))

    return X, Y




def QE_pdos(prefix, emin, emax, de, projections, Ef, outfile_prefix, do_convolve, de_new, var, nspin=1):
    """Computes various types of pDOS from the atomic state projections generated by the QE

    Args:
        prefix ( string ): a common prefix of the filenames for files containing the projection information
        emin ( double ): the minimal energy of the pDOS window [eV]
        emax ( double ): maximal energy of the pDOS window [eV]
        de ( double ): the original grid spacing of the pDOS [eV] (not necessarily the one used in pdos.in)
        projections ( list of lists of - see below): groups of atoms and types of projections.
            Each element of this list contains 3 sub-lists, whose intersection defines which files to use:
            e.g. projection = [["s","p"], [1,2,3], ["Cs", "Br"]] - means s and p orbitals of atoms 1, 2, and 3
            as long as any of these atoms are Cs or Br
        Ef ( double ): which energy use as the origin of energy scale (zero) in the output. Usually 
            the Fermi or LUMO energy
        outfile_prefix ( string ): the prefix of the output file that will contain the final projections
        do_convolve ( Bool ): the flag telling whether we want to convolve the original data with the
            Gaussian envelope. The convolution is done with :func:`convolve`
        de_new ( double ): the new energy grid spacing [eV], in effect only if do_convolve == True
        var ( double ): standard deviation of the Gaussian [eV] with which we do a convolution, 
            in effect only if do_convolve == True
        nspin ( int): specifies which nspin was used in the electronic structure calculation.
                      nspin = 1      
                      nspin = 2
                      nspin = 4

    Returns:
        tuple: ( E, pDOSa ), where:

            * E ( MATRIX(N, 1) ): new energy grid, N - the new number of energy grid points
            * pDOSa ( MATRIX(N, Nproj) ): new Y grids, Nproj - len(projections) the number of projections we are interested in
            * if spin = 2, returns pDOSb for beta spin-orbtials as well
            * if spin = 4, returns just the pDOSa (pDOSb = None), but the orbitals now mixed spin states 
    """

    if nspin not in [1,2,4]:
        print ("Error: The value of nspin must be either 1, 2, or 4")
        print ("nspin = 1: Spin-unpolarized")
        print ("nspin = 2: Spin-polarized")
        print ("nspin = 4: Spin-non-colinear")
        print ("Exiting Now ...")
        sys.exit(0)

    #============= Dimensions  =================

    nproj = len(projections)                # number of projections
    N = int(math.floor((emax - emin)/de))+1 # number of the gridpoints

    en   = MATRIX(N, 1)      # energy of the grid points
    dosa = MATRIX(N, nproj)  # Matrix for alpha spin-orbitals dos.get(i,proj) - dos for level i projected on projection proj
    dosb = MATRIX(N, nproj)  # Matrix for beta  spin-orbitals
    for i in range(0,N):
        en.set(i, 0, emin + i*de - Ef)

        #============= Data gathering  =================

    for proj in projections:  # loop over all projection
        ang_mom = proj[0]
        atoms = proj[1]
        elements = proj[2]

        proj_indx = projections.index(proj)

        for a in atoms: # open files for atoms with given indices (indexing from 1)
            for symb in ang_mom:  # for given angular momentum labels
                for wfc in range(0,5): # Specify max wfc type index - usually no more than 3, 5 - should be more than enough  
                    for Elt in elements: # for given atom names

                        if nspin == 4:
                            for k in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]: # total angular momentum label
                                filename = prefix+str(a)+"("+Elt+")_wfc#"+str(wfc)+"("+symb+"_j"+str(k)+")"
                                if os.path.exists(filename):

                                    fa = open(filename,"r")
                                    B = fa.readlines()
                                    check = B[0].split()
                                    fa.close()

                                    for lin in B[1:]:  # read all lines, except for the header
                                        tmp = lin.split()
                                        e = float(tmp[0])
                                        if e<emin or e>emax:
                                            pass
                                        else:
                                            state_indx = int(math.floor((e - emin)/de))
                                            dosa.add(state_indx, proj_indx, float(tmp[1]))

                        else:

                            filename = prefix+str(a)+"("+Elt+")_wfc#"+str(wfc)+"("+symb+")"  # file 
                            if os.path.exists(filename):

                                fa = open(filename,"r")
                                B = fa.readlines()
                                check = B[0].split()
                                fa.close()

                                for lin in B[1:]:  # read all lines, except for the header
                                    tmp = lin.split()

                                    e = float(tmp[0])
                                    if e<emin or e>emax:
                                        pass
                                    else:
                                        state_indx = int(math.floor((e - emin)/de))
                                        dosa.add(state_indx, proj_indx, float(tmp[1]))
                                        if nspin == 2 and check[4] == "ldosdw(E)":
                                            dosb.add(state_indx, proj_indx, float(tmp[2]))

    #============= Optional convolution =================

    E, pDOSa, pDOSb = en, dosa, dosb
    if do_convolve==True:
        E, pDOSa = convolve(en, dosa, de, de_new, var)
        E, pDOSb = convolve(en, dosb, de, de_new, var)

    #============= Print out ==================
    f2a = open(outfile_prefix+"_alp.txt","w"); f2a.close()
    f2b = open(outfile_prefix+"_bet.txt","w"); f2b.close()

    N = E.num_of_rows
    for i in range(0,N):  # loop over grid points
        line = str(E.get(i,0))+"   "
        tot = 0.0
        for j in range(0,nproj):
            tot = tot + pDOSa.get(i,j)
            line = line + str(pDOSa.get(i,j))+"   "
        line = line + str(tot)+"\n"
        f2a = open(outfile_prefix+"_alp.txt","a")
        f2a.write(line)
        f2a.close()

    for i in range(0,N):  # loop over grid points
        line = str(E.get(i,0))+"   "
        tot = 0.0
        for j in range(0,nproj):
            tot = tot + pDOSb.get(i,j)
            line = line + str(pDOSb.get(i,j))+"   "
        line = line + str(tot)+"\n"
        f2b = open(outfile_prefix+"_bet.txt","a")
        f2b.write(line)
        f2b.close()

    if nspin == 2:
        return E, pDOSa, pDOSb
    else:
        pDOSb = MATRIX(pDOSa)
        return E, pDOSa, pDOSb



def libra_pdos(_emin, _emax, _de, projections, prefix, outfile, Nel, do_convolve, _de_new, _var):
    """
    
    Args:
    
        * _emin ( double ): minimal energy of the spectrum [eV]
        
        * _emax ( double ): maximal energy of the spectrum [eV]
        
        * _de ( double ): original energy grid spacing  [eV]
        
        * projections ( list ):  groups of atoms and types of projections 
            e.g. projections = [["s",[1,2,3]], ["p",[1,2,3]], ... 
            
            Possible projections (examples)
            proj = [["s",range(0,360)],["p",range(0,360)],["d",range(0,360)]]
            proj = [["s",range(0,1)],["p",range(0,1)],["d",range(0,1)]]
            proj = [["tot",range(0,112)]]

            
        * prefix ( string ): the common prefix of the files containing the projection information
        
        * outfile ( string ): the name of the file that will contain the computed pDOSs
        
        * Nel ( int ): the number of electrons, to compute the Fermi energy
            
        * _de_new ( double ): new energy grid (for convolved) spacing  [eV]
        
        * _var ( double ): the width of the Gaussian used to broaden each energy grid point [eV] 
        
        
    # Example: of call - for Si QD
    # Si
    #main(-35.0, 35.0, 0.1,[["tot",range(0,103)]],"_alpha_wfc_atom","dos_proj.txt",238)   

    """
    
    # Internally, we work in a.u. (Ha)
    emin = _emin * units.ev2Ha
    emax = _emax * units.ev2Ha
    de = _de * units.ev2Ha
    de_new = _de_new * units.ev2Ha
    var = _var * units.ev2Ha

    # Determine dimensionality and prepare arrays
    nproj = len(projections)                # number of projections
    N = int(math.floor((emax - emin)/de))+1 # number of the gridpoints

    en0 = []
    dosa = MATRIX(N, nproj)  # Matrix for alpha spin-orbitals dos.get(i,proj) - dos for level i projected on projection proj
    dosb = MATRIX(N, nproj)  # Matrix for beta  spin-orbitals
    
    
    for proj in projections:  # loop over all projection
        ang_mom = proj[0]
        atoms = proj[1]

        proj_indx = projections.index(proj)
                                            
        for a in atoms: # open files for all atoms in given group
            fa = open(prefix+str(a),"r")
            B = fa.readlines()
            fa.close()

            for lin in B[1:-4]:  # read all lines
                tmp = lin.split()
                 
                e = float(tmp[0]) # energy in Ha
                if a==0:
                    en0.append(e)  
                
                x = 0.0
                if ang_mom=="s":
                    x = float(tmp[2])
                elif ang_mom=="p":
                    x = float(tmp[3])
                elif ang_mom=="d":
                    x = float(tmp[4])
                elif ang_mom=="tot":
                    x = float(tmp[1])
                else:
                    x = 0.0

                if e<emin or e>emax:
                    pass
                else:
                    grid_indx = int(math.floor((e - emin)/de))  # grid point
                    dosa.add(grid_indx, proj_indx, x)
                    dosb.add(grid_indx, proj_indx, x)


    
    etol = 1e-10
    kT = 0.1 * units.ev2Ha # some reasonable parameters
    Ef = fermi_energy(en0, Nel,2.0, kT, etol)  # Fermi energy in Ha
    

    en = MATRIX(N,1)
    for i in range(0,N):
        en.set(i, 0, emin + i*de - Ef)

    
    E = None                
    if do_convolve==True:
        E, pDOSa = convolve(en, dosa, de, de_new, var)
        #E, pDOSb = convolve(en0, dosb, de, de_new, var)
    else:
        E = MATRIX(dosa)
            
    # Convert the energy axis back to eV 
    E *= (1.0/units.ev2Ha)

        
    f2 = open(outfile,"w")
    f2.write("Ef = %5.3f eV\n" % (Ef / units.ev2Ha) )
    f2.close()

    
    res = np.zeros( (N, nproj+2), dtype=float)
    
    # Now compute projections
    for i in range(0,N):  # loop energy grid

        res[i, 0] = E.get(i,0) 
        line = str(E.get(i,0))+"   "

        tot = 0.0
        for j in range(0,nproj):
            res[i, j+1] = pDOSa.get(i,j)
            tot = tot + pDOSa.get(i,j)
            line = line + str(pDOSa.get(i,j))+"   "
            
        res[i, nproj+1] = tot
        line = line + str(tot)+"\n"

        f2 = open(outfile,"a")
        f2.write(line)
        f2.close()
    

    return res
    

def convolve_cp2k_pdos(params: dict):
    """
    This function reads the pdos file produced by CP2K and extract the pdos at each time step and 
    then convolve them with Gaussian functions.
    
    Args:
    
        params (dictionary):
    
            cp2k_pdos_file (str): The CP2K .pdos file.
        
            time_step (int): The time step of molecular dynamics.
        
            sigma (float): The standard deviation in Gaussian function.
        
            coef (float): The coefficient multiplied in Gaussian function.
        
            npoints (int): The number of points used in convolution.
        
            energy_conversion (float): The energy conversion unit from Hartree. For example 27.211386 is
                                       for unit conversion from Hartree to eV. This value comes from libra_py.units. For example
                                       for Hartree to eV one needs to call libra_py.units.au2ev in the input. The default value is 
                                       Hartree to eV.
				   
            angular_momentum_cols (list): The angular momentum columns in the *.pdos files produced by CP2K.
	
    Returns:
	
        energy_grid (numpy array): The energy grid points vector.
		
        convolved_pdos (numpy array): The convolved pDOS vector.
		
        homo_energy (float): The average HOMO energy.
		
    """

    # Critical parameters
    critical_params = [ "cp2k_pdos_file", "angular_momentum_cols"]
    # Default parameters
    default_params = { "time_step": 0, "sigma": 0.02, "coef": 1.0, "npoints": 4000, "energy_conversion": units.au2ev }
    # Check input
    comn.check_input(params, default_params, critical_params) 

    # The CP2K log file name
    cp2k_pdos_file = params["cp2k_pdos_file"]
    # The time step in the .pdos file (This is for molecular dynamics, for single-point calculations it is set to 0).
    time_step = params["time_step"]
    # The standard deviation value
    sigma = params["sigma"]
    # The pre factor that is multiplied to the Gaussian function
    coef = params["coef"]
    # Number of points for the grid 
    npoints = params["npoints"]
    # The energy conversion value from atomic unit, It is better to use the default values in the `libra_py.units`
    energy_conversion = params["energy_conversion"]
    # The angular momentum columns in the .pdos files
    angular_momentum_cols = params["angular_momentum_cols"]

    # Opening the file
    file = open(cp2k_pdos_file,'r')
    lines = file.readlines()
    file.close()
    
    # Lines with 'DOS'
    lines_with_dos = []
    
    # Finding the lines with 'DOS'
    for i in range(0,len(lines)):
        if 'DOS'.lower() in lines[i].lower().split():
            lines_with_dos.append(i)
    
    # Finding the first and last index of PDOS for each time step
    if len(lines_with_dos)==1:
        # First index
        first_index = 2
        # Last index
        last_index = int(lines[len(lines)-1].split()[0])
    elif len(lines_with_dos)>1:
        # First index
        first_index = 2
        # Last index
        last_index = int(lines_with_dos[1]-1)
    
    # Find the number of columns in the PDOS file showing the number 
    # of orbital components, energy, and occupation column.
    num_cols = len(lines[first_index].split())
    
    # Number of energy levels considered for PDOS
    num_levels = last_index - first_index + 1

    
    # Finding the homo and lumo energy level by appending the 
    # pdos numerical values of unoccupied states only
    pdos_unocc = []
    # Energy levels
    energy_levels = []
    for i in range(first_index, last_index + 1):
        energy_levels.append(float(lines[i].split()[1])*energy_conversion)
        if float(lines[i].split()[2])==0:
            pdos_unocc.append(i)
    # HOMO energy level
    homo_level = int(lines[min(pdos_unocc)].split()[0])
    # HOMO energy
    homo_energy = float(lines[homo_level].split()[1])*energy_conversion
    # Minimum energy level
    min_energy = float(lines[first_index].split()[1])*energy_conversion
    # Maximum energy level
    max_energy = float(lines[last_index].split()[1])*energy_conversion
    
    
    # Now we make an equispaced energy vector from min_energy ad max_energy with npoints.
    energy_grid = np.linspace( min_energy-2, max_energy+2, npoints )
    energy_grid = np.array(energy_grid)
    
    
    # Appending the energy lines with their component densities of states
    energy_lines = []
    # The initial line in the .pdos file of step 'time_step'
    init_line  = time_step * ( num_levels + 2 ) + 2
    # The final line in the .pdos file of step 'time_step'
    final_line = ( time_step + 1 ) * ( num_levels + 2 )
    for i in range( init_line, final_line ):
        # Appending the energy lines into enrgy_lines
        energy_lines.append( lines[i].split() )

    for i in range(0, len(energy_lines)):
        
        for j in range(0,len(energy_lines[0])):
            
            energy_lines[i][j] = float(energy_lines[i][j])
            
    energy_lines = np.array(energy_lines)

    # Now we sum the PDOSs defined in angular_momentum_cols by user
    pdos_sum = []
    for k in range(0, len(energy_lines)):
        
        # A temporary vector for summation of the PDOS
        tmp_vec = []
        tmp_vec.append(energy_lines[k][1])
        
        for i in range(0,len(angular_momentum_cols)):
            # Initializing a new sum variable
            # print("angular_momentum_cols[i]",angular_momentum_cols[i])
            tmp_sum = 0
            for j in angular_momentum_cols[i]:
                
                # If j is less than the number of columns 
                # then sum the PDOS
                if j<=num_cols:
                    tmp_sum += energy_lines[k][j]
            # Appending tmp_sum into tmp_vec
            tmp_vec.append(tmp_sum)
        
        # Now append tmp_vec into pdos_sum, we will
        # then use this pdos_sum for convolution
        pdos_sum.append(tmp_vec)
    
    convolved_pdos = []
    t1 = time.time()
    # The pre-factor for Gaussian functions
    pre_factor = (coef/(sigma*np.sqrt(2.0*np.pi)))
    for j in range(1,len(angular_momentum_cols)+1):
        # Initialize a vector of zeros summing the weighted PDOS
        tmp_weighted_pdos = np.zeros(energy_grid.shape)

        for i in range(0,num_levels):
            # The Guassian function
            gaussian_fun = pre_factor*(np.exp(-0.5*np.power(((energy_grid-float(pdos_sum[i][0])*energy_conversion)/sigma),2)))
            
            tmp_weighted_pdos = tmp_weighted_pdos + gaussian_fun * float( pdos_sum[i][j] )
        convolved_pdos.append(tmp_weighted_pdos)
    print('Elapsed time for convolving ',cp2k_pdos_file,': ',time.time()-t1,' seconds')
    convolved_pdos = np.array(convolved_pdos)
    
    return energy_grid, convolved_pdos, homo_energy
   
   
