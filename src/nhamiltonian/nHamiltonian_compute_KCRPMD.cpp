/*********************************************************************************
* Copyright (C) 2018-2022 Alexey V. Akimov
*
* This file is distributed under the terms of the GNU General Public License
* as published by the Free Software Foundation, either version 3 of
* the License, or (at your option) any later version.
* See the file LICENSE in the root directory of this distribution
* or <http://www.gnu.org/licenses/>.
*
*********************************************************************************/
/**
  \file nHamiltonian_compute_KCRPMD.cpp
  \brief The file implements the calculations of the KC-RPMD (Kinetically Constrained Ring Polymer Molecular Dynamics)
  terms 
    
*/

#if defined(USING_PCH)
#include "../pch.h"
#else
#include <stdlib.h>
#endif 

#include "nHamiltonian.h"
#include "../math_meigen/libmeigen.h"

/// liblibra namespace
namespace liblibra{

/// libnhamiltonian namespace 
namespace libnhamiltonian{


using namespace liblinalg;
using namespace libmeigen;


vector<MATRIX> nHamiltonian::generate_m_matrices(double beta){
/**
  Generate set of M matrices for each trajectory

  beta - the inverse temperature Boltzmann factor in atomic units
*/

  if(ham_dia_mem_status==0){ cout<<"Error in generate_m_matrices(): the diabatic Hamiltonian matrix is not allocated \
  but it is needed for the calculations\n"; exit(0); }

  if(ndia!=2){ cout<<"Error in generate_m_matrices(): implementation only for ndia=2\n"; exit(0); }

  vector<MATRIX> res;

  if(children.size()==0){
    res = vector<MATRIX>(1, MATRIX(2,2));
    double V0 = (ham_dia->get(0,0)).real(); 
    double V1 = (ham_dia->get(1,1)).real(); 
    double K = abs(ham_dia->get(0,1)); 
    res[0].set(0,0, exp(-beta * V0));
    res[0].set(0,1, -beta * K * exp(-beta * V0));
    res[0].set(1,0, -beta * K * exp(-beta * V1));
    res[0].set(1,1, exp(-beta * V1));
  }
  else{
    res = vector<MATRIX>(children.size(), MATRIX(2,2));
    for(int traj=0; traj<children.size(); traj++){
      double V0 = (children[traj]->ham_dia->get(0,0)).real(); 
      double V1 = (children[traj]->ham_dia->get(1,1)).real(); 
      double K = abs(children[traj]->ham_dia->get(0,1));
      res[traj].set(0,0, exp(-beta / children.size() * V0));
      res[traj].set(0,1, -beta / children.size() * K * exp(-beta / children.size() * V0));
      res[traj].set(1,0, -beta / children.size() * K * exp(-beta / children.size() * V1));
      res[traj].set(1,1, exp(-beta / children.size() * V1));
    }
  }
  return res;
}


double nHamiltonian::kcrpmd_effective_potential(vector<double>& y_aux_var, const MATRIX& q, const MATRIX& invM, double beta, double eta, double a, double b, double c, double d){
/**
  Compute the KC-RPMD effective potential energy

  y_aux_var - is the classical electronic coordinate as defined in KC-RPMD
  q - is a ndof x ntraj matrix of coordinates
  invM - is a ndof x 1 matrix of inverse masses of all DOFs
  beta - the inverse temperature Boltzmann factor in atomic units
  eta - geometric parameter conserving free energy of kinked pair formation ad defined in second KC-RPMD paper
  a - is the kinetic constraint ad-hoc parameter
  b - is the heavyside functional limit parameter
  c - is the constraint switching parameter
  d - is the free energy conservation switching parameter
*/

  if(ham_dia_mem_status==0){ cout<<"Error in kcrpmd_effective_potential(): the diabatic Hamiltonian matrix is not allocated \
  but it is needed for the calculations\n"; exit(0); }

  if(ndia!=2){ cout<<"Error in kcrpmd_effective_potential(): implementation only for ndia=2\n"; exit(0); }

  int ndof = q.n_rows;
  int ntraj = q.n_cols;

  double V0;
  double V1;
  double VKP;
  double res;

  if(children.size()==1 and ntraj==1){ 
    //============ Compute the pure electronic contributions =========  
    V0 = (children[0]->ham_dia->get(0,0)).real(); 
    V1 = (children[0]->ham_dia->get(1,1)).real(); 
    double K = abs(children[0]->ham_dia->get(0,1)); 
    // double Vg = (children[0]->ham_adi->get(0,0)).real();
    // double Ve = (children[0]->ham_adi->get(1,1)).real(); 
    double Vg = 0.5 * (V0 + V1) - 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    double Ve = 0.5 * (V0 + V1) + 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    if(beta * K > 1e-3){
      VKP = Vg - log(1 + exp(-beta * (Ve - Vg)) - exp(-beta * (V0 - Vg)) - exp(-beta * (V1 - Vg))) / beta;
    }
    else if(beta * abs(V0 - V1) > 1e-7){
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2) * sinh(0.5 * beta * (V0 - V1)) / (0.5 * beta * (V0 - V1))) / beta;
    }
    else{
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2)) / beta;
    }

    //============ Compute the kinetic constraint =========  
    double w = (V0 - V1) / K;
    double A = 0.5 * a * (1 + tanh(-c * (beta * K - 1)));
    double C = 1 + 0.5 * (sqrt(A / 3.1415) * eta - 1) * (1 + tanh(-d * (beta * K - 1)));
    VKP += (A * pow(w, 2) - log(C)) / beta;

    //============ Compute the heavy side auxiliary potentials =========  
    if(abs(y_aux_var[0] + 1) < 0.5){
      V0 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] + 1) - 1)))) / beta;
    }
    else{
      V0 += (b * (2 * abs(y_aux_var[0] + 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] + 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0] - 1) < 0.5){
      V1 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] - 1) - 1)))) / beta;
    }
    else{
      V1 += (b * (2 * abs(y_aux_var[0] - 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] - 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0]) < 0.5){
      VKP += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0]) - 1)))) / beta;
    }
    else{
      VKP += (b * (2 * abs(y_aux_var[0]) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0]) - 1))))) / beta;
    }
  }
  else if(children.size()==ntraj){
    cout<<"Error in kcrpmd_effective_potential() not implemented for quantum nuclei\n"; exit(0);
  }
  else{
    cout<<"ERROR: the size of the input is different from the number of children\n"; exit(0); 
  }
  
  double Vshift = min({V0, VKP, V1});

  res = RPMD_internal_potential(q,invM,beta) + Vshift - log(exp(-beta * (V0 - Vshift)) + exp(-beta * (VKP - Vshift)) + exp(-beta * (V1 - Vshift))) / beta;

  return res;
}


MATRIX nHamiltonian::kcrpmd_effective_force(vector<double>& y_aux_var, const MATRIX& q, const MATRIX& invM, double beta, double eta, double a, double b, double c, double d){
/**
  Compute the KC-RPMD effective nuclear force

  y_aux_var - is the classical electronic coordinate as defined in KC-RPMD
  q - is a ndof x ntraj matrix of coordinates
  invM - is a ndof x 1 matrix of inverse masses of all DOFs
  beta - the inverse temperature Boltzmann factor in atomic units
  eta - geometric parameter conserving free energy of kinked pair formation ad defined in second KC-RPMD paper
  a - is the kinetic constraint ad-hoc parameter
  b - is the heavyside functional limit parameter
  c - is the constraint switching parameter
  d - is the free energy conservation switching parameter
*/

  if(ham_dia_mem_status==0){ cout<<"Error in kcrpmd_effective_potential(): the diabatic Hamiltonian matrix is not allocated \
  but it is needed for the calculations\n"; exit(0); }

  if(ndia!=2){ cout<<"Error in kcrpmd_effective_potential(): implementation only for ndia=2\n"; exit(0); }

  int ndof = q.n_rows;
  int ntraj = q.n_cols;
  int dof;

  double V0;
  double V1;
  double VKP;

  MATRIX F0(ndof, ntraj);
  MATRIX F1(ndof, ntraj);
  MATRIX FKP(ndof, ntraj);
  MATRIX res(ndof, ntraj);

  if(children.size()==1 and ntraj==1){ 
    //============ Compute the pure electronic contributions =========  
    V0 = (children[0]->ham_dia->get(0,0)).real(); 
    V1 = (children[0]->ham_dia->get(1,1)).real(); 
    double K = abs(children[0]->ham_dia->get(0,1)); 
    // double Vg = (children[0]->ham_adi->get(0,0)).real();
    // double Ve = (children[0]->ham_adi->get(1,1)).real(); 
    double Vg = 0.5 * (V0 + V1) - 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    double Ve = 0.5 * (V0 + V1) + 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    if(beta * K > 1e-3){  
      VKP = Vg - log(1 + exp(-beta * (Ve - Vg)) - exp(-beta * (V0 - Vg)) - exp(-beta * (V1 - Vg))) / beta;
    }
    else if(beta * abs(V0 - V1) > 1e-7){
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2) * sinh(0.5 * beta * (V0 - V1)) / (0.5 * beta * (V0 - V1))) / beta;
    }
    else{
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2)) / beta;
    }

    MATRIX FK(ndof, ntraj);
    MATRIX Fg(ndof, ntraj);
    MATRIX Fe(ndof, ntraj);
    for(dof=0; dof<ndof; dof++){   
      F0.set(dof, 0, -(children[0]->d1ham_dia[dof]->get(0,0)).real());
      F1.set(dof, 0, -(children[0]->d1ham_dia[dof]->get(1,1)).real());
      FK.set(dof, 0, -(children[0]->d1ham_dia[dof]->get(0,1)).real());
      //FK.set(dof, 0, -abs(children[0]->d1ham_dia[dof]->get(0,1)));
      // cout << "K: " << children[0]->ham_dia->get(0,1) << " |K|: " << K << " dK:" << children[0]->d1ham_dia[dof]->get(0,1) << endl;
      // Fg.set(dof, 0, -(children[0]->d1ham_adi[dof]->get(0,0)).real());
      // Fe.set(dof, 0, -(children[0]->d1ham_adi[dof]->get(1,1)).real());
    }// for dof
    Fg = 0.5 * (F0 + F1) - ((V0 - V1) * (F0 - F1) + 4 * K * FK) / (2 * sqrt(pow(V0 - V1, 2) + pow(2 * K, 2)));
    Fe = 0.5 * (F0 + F1) + ((V0 - V1) * (F0 - F1) + 4 * K * FK) / (2 * sqrt(pow(V0 - V1, 2) + pow(2 * K, 2)));
    if(beta * K > 1e-3){  
      //cout<<K<<" <-|K|, VKP-> " << VKP << endl;
      FKP = (Fg + exp(-beta * (Ve - Vg)) * Fe - exp(-beta * (V0 - Vg)) * F0 - exp(-beta * (V1 - Vg)) * F1) / (1 + exp(-beta * (Ve - Vg)) - exp(-beta * (V0 - Vg)) - exp(-beta * (V1 - Vg)));
      //cout<<FKP<<endl;
    }
    else if(beta * abs(V0 - V1) > 1e-7){
      //cout << "Here 1" << endl;
      FKP = 0.5 * (F0 + F1) + (F0 - F1) * (1 / (beta * (V0 - V1)) - 0.5 * cosh(0.5 * beta * (V0 - V1)) / sinh(0.5 * beta * (V0 - V1))) - 2 * FK / (beta * K);
    }
    else{
      // cout << "Here 2" << endl;
      //cout<<(children[0]->ham_dia->get(0,0))<<endl; 
      //cout<<(children[0]->ham_dia->get(0,1))<<endl; 
      //cout<<K<<" <-|K|, Fk? " << FK << endl;
      //cout<<"Error in kcrpmd_effective_potential()?\n"; exit(0); 
      FKP = 0.5 * (F0 + F1) - 2 * FK / (beta * K);
    }

    //============ Compute the kinetic constraint =========  
    double w = (V0 - V1) / K;
    double A = 0.5 * a * (1 + tanh(-c * (beta * K - 1)));
    double C = 1 + 0.5 * (sqrt(A / 3.1415) * eta - 1) * (1 + tanh(-d * (beta * K - 1)));
    VKP += (A * pow(w, 2) - log(C)) / beta;

    MATRIX Fw(ndof, ntraj);
    MATRIX FA(ndof, ntraj);
    MATRIX FC(ndof, ntraj);
    Fw = (F0 - F1 - w * FK) / K;
    if(c * abs(beta * K - 1) < 250.){
      FA = -0.5 * a * c * beta / pow(cosh(-c * (beta * K - 1)), 2) * FK;
    }
    //cout << "FC Before: " << FC << " A: " << A << " FA: " << FA << " Ratio: " << FA / sqrt(A)<<endl;
    FC = -eta / (4 * sqrt(3.1415)) * (1 + tanh(-d * (beta * K - 1))) * FA / sqrt(A); 
    //cout << "FC Halfway: " << FC << endl;
    if(d * abs(beta * K - 1) < 250.){
      FC += -0.5 * d * beta * (sqrt(A / 3.1415) * eta - 1) / pow(cosh(-d * (beta * K - 1)), 2) * FK;
    }
    //cout << "FC After: " << FC << endl;
    //cout << "FKP Before: " << FKP << " FA: " << FA << " FC: " << FC << endl;
    FKP += (w * w * FA + 2 * A * w * Fw - FC / C) / beta;
    //cout << "FKP After: " << FKP << endl;

    //============ Compute the heavy side auxiliary potentials =========  
    if(abs(y_aux_var[0] + 1) < 0.5){
      V0 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] + 1) - 1)))) / beta;
    }
    else{
      V0 += (b * (2 * abs(y_aux_var[0] + 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] + 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0] - 1) < 0.5){
      V1 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] - 1) - 1)))) / beta;
    }
    else{
      V1 += (b * (2 * abs(y_aux_var[0] - 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] - 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0]) < 0.5){
      VKP += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0]) - 1)))) / beta;
    }
    else{
      VKP += (b * (2 * abs(y_aux_var[0]) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0]) - 1))))) / beta;
    }
  }
  else if(children.size()==ntraj){
    cout<<"Error in kcrpmd_effective_potential() not implemented for quantum nuclei\n"; exit(0);
  }
  else{
    cout<<"ERROR: the size of the input is different from the number of children\n"; exit(0); 
  }
  
  double Vshift = min({V0, VKP, V1});
  
  res = RPMD_internal_force(q,invM,beta) + (exp(-beta * (V0 - Vshift)) * F0 + exp(-beta * (VKP - Vshift)) * FKP + exp(-beta * (V1 - Vshift)) * F1) / (exp(-beta * (V0 - Vshift)) + exp(-beta * (VKP - Vshift)) + exp(-beta * (V1 - Vshift)));


  // cout<<"VKP: " << VKP << "FKP: "<<FKP<< " " <<abs(children[0]->ham_dia->get(0,1))<<" <-|K|, Fk? " << " FKCRPMD = " << res << endl;
  return res;
}


vector<double> nHamiltonian::kcrpmd_effective_auxiliary_force(vector<double>& y_aux_var, double beta, double eta, double a, double b, double c, double d){
/**
  Compute the KC-RPMD effective auxiliary force

  y_aux_var - is the classical electronic coordinate as defined in KC-RPMD
  beta - the inverse temperature Boltzmann factor in atomic units
  eta - geometric parameter conserving free energy of kinked pair formation ad defined in second KC-RPMD paper
  a - is the kinetic constraint ad-hoc parameter
  b - is the heavyside functional limit parameter
  c - is the constraint switching parameter
  d - is the free energy conservation switching parameter
*/

  if(ham_dia_mem_status==0){ cout<<"Error in kcrpmd_effective_potential(): the diabatic Hamiltonian matrix is not allocated \
  but it is needed for the calculations\n"; exit(0); }

  if(ndia!=2){ cout<<"Error in kcrpmd_effective_potential(): implementation only for ndia=2\n"; exit(0); }

  int ntraj = children.size();   

  double V0;
  double V1;
  double VKP;

  double F0;
  double F1;
  double FKP;
  vector<double> res;

  if(ntraj==1){ 
    //============ Compute the pure electronic contributions =========  
    V0 = (children[0]->ham_dia->get(0,0)).real(); 
    V1 = (children[0]->ham_dia->get(1,1)).real(); 
    double K = abs(children[0]->ham_dia->get(0,1)); 
    // double Vg = (children[0]->ham_adi->get(0,0)).real();
    // double Ve = (children[0]->ham_adi->get(1,1)).real(); 
    double Vg = 0.5 * (V0 + V1) - 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    double Ve = 0.5 * (V0 + V1) + 0.5 * sqrt(pow((V0 - V1), 2) + pow(2 * K, 2));
    if(beta * K > 1e-3){
      VKP = Vg - log(1 + exp(-beta * (Ve - Vg)) - exp(-beta * (V0 - Vg)) - exp(-beta * (V1 - Vg))) / beta;
    }
    else if(beta * abs(V0 - V1) > 1e-7){
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2) * sinh(0.5 * beta * (V0 - V1)) / (0.5 * beta * (V0 - V1))) / beta;
    }
    else{
      VKP = 0.5 * (V0 + V1) - log(pow(beta * K, 2)) / beta;
    }

    //============ Compute the kinetic constraint =========  
    double w = (V0 - V1) / K;
    double A = 0.5 * a * (1 + tanh(-c * (beta * K - 1)));
    double C = 1 + 0.5 * (sqrt(A / 3.1415) * eta - 1) * (1 + tanh(-d * (beta * K - 1)));
    VKP += (A * pow(w, 2) - log(C)) / beta;

    //============ Compute the heavy side auxiliary potentials =========  
    if(abs(y_aux_var[0] + 1) < 0.5){
      V0 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] + 1) - 1)))) / beta;
    }
    else{
      V0 += (b * (2 * abs(y_aux_var[0] + 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] + 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0] - 1) < 0.5){
      V1 += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0] - 1) - 1)))) / beta;
    }
    else{
      V1 += (b * (2 * abs(y_aux_var[0] - 1) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0] - 1) - 1))))) / beta;
    }
    if(abs(y_aux_var[0]) < 0.5){
      VKP += -log(1 / (1 + exp(b * (2 * abs(y_aux_var[0]) - 1)))) / beta;
    }
    else{
      VKP += (b * (2 * abs(y_aux_var[0]) - 1) - log(1 / (1 + exp(-b * (2 * abs(y_aux_var[0]) - 1))))) / beta;
    }

    if(y_aux_var[0] + 1 > 0.0){
      F0 += -b * (1 + tanh(b * (abs(y_aux_var[0] + 1) - 0.5))) / beta;
    }
    else{
      F0 += b * (1 + tanh(b * (abs(y_aux_var[0] + 1) - 0.5))) / beta;
    }
    if(y_aux_var[0] > 0.0){
      FKP += -b * (1 + tanh(b * (abs(y_aux_var[0]) - 0.5))) / beta;
    }
    else{
      FKP += b * (1 + tanh(b * (abs(y_aux_var[0]) - 0.5))) / beta;
    }
    if(y_aux_var[0] - 1 > 0.0){
      F1 += -b * (1 + tanh(b * (abs(y_aux_var[0] - 1) - 0.5))) / beta;
    }
    else{
      F1 += b * (1 + tanh(b * (abs(y_aux_var[0] - 1) - 0.5))) / beta;
    }
  }
  else{
    cout<<"Error in kcrpmd_effective_auxiliary_force() not implemented for quantum nuclei\n"; exit(0);
  }
 
  double Vshift = min({V0, VKP, V1});
  
  res = vector<double>(1, (exp(-beta * (V0 - Vshift)) * F0 + exp(-beta * (VKP - Vshift)) * FKP + exp(-beta * (V1 - Vshift)) * F1) / (exp(-beta * (V0 - Vshift)) + exp(-beta * (VKP - Vshift)) + exp(-beta * (V1 - Vshift))));

  return res;
}






}// namespace libnhamiltonian
}// liblibra

