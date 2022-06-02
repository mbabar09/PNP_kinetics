from __future__ import print_function
import numpy as np
import os, sys, re, glob
from dolfin import *
from fenics import *
import pickle
from numpy.random import rand
from numpy.linalg import norm
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import matplotlib as mpl
font = {'family' : 'Times New Roman',
        'weight' : 'regular',
        'size'   : 16}

mpl.rc('font', **font)
mpl.rcParams['figure.figsize'] = (10.0, 6.0)
mpl.rc('axes', linewidth=2)
mpl.rcParams['lines.linewidth'] = 2
#mpl.rcParams['xtick.major.size'] = 20                                                                                                                                     
mpl.rcParams['xtick.major.width'] = 2
mpl.rcParams['ytick.major.width'] = 2

def save_obj(obj, name ):
    with open(name, 'wb') as f:
        pickle.dump(obj, f)

def load_obj(name ):
    with open(name, 'rb') as f:
        return pickle.load(f)
    
def get_current(func, mesh, a_s = 1e-7):
    # func: _c_3 in our case (Ru3+), a_s: 100nm pippete radius
    F = 96485.332
    r = np.linspace(0,a_s,1000)
    Jo_list = []
    vec = project(func.dx(1), FunctionSpace(mesh, P1))
    for j in range(len(r)):
        point = np.array([r[j], 0.0])
        x = np.array(point)
        x_point = Point(*x) 
        Jo = -D_o*vec(x_point)
        Jo_list.append(Jo)
    i = 2*np.pi*F*np.trapz(Jo_list*r, x=r)
    return i

def BV_rates(ko, Eo, A=1.0, Vapp=0.0, alpha=0.5):
    kbT = 0.0259
    kox = A*ko*np.exp(-(alpha*(Vapp - Eo))/kbT)
    kred = A*ko*np.exp(-((1-alpha)*(Vapp - Eo))/kbT)
    return kox, kred

c_0 = load_obj('initial_c0.pkl')

loc = '../'
mesh = Mesh(loc+'mesh.xml');
cd=MeshFunction('size_t',mesh,loc+'mesh_physical_region.xml')
fd=MeshFunction('size_t',mesh,loc+'mesh_facet_region.xml')

## Constants Radial
z_1, z_2, z_3, z_4 = 1, -1, 3, 2 # Charge numbers K+, Cl-, Ru3+, Ru2+
eps = 80
eps0 = 8.854187e-12 # Vacuum permittivity F/m
e = 1.60218e-19 # Coulombs 
kbT = 0.0259 # eV, room temp
F = 96485.332 # C/mol
Eo = -0.07
D_o, D_r = 6.5e-10, 6.5e-10 # Diff constants (m^2/s)
a = (1/kbT)
b = a*(F/(eps*eps0))
#a, b = 1, 10e14
eta_list = np.linspace(-0.5, 0.5, 30)
Vapp_list = eta_list + Eo
idx = 0
phi_z0 = 10

## initialize phi
V_phi = FunctionSpace(mesh, 'P', 1)

phi_D = Expression(str(0.0), degree=1)
phi_L = Expression(str(phi_z0), degree=1)

def boundary(x, on_boundary):
    return on_boundary

phi = TrialFunction(V_phi)
v = TestFunction(V_phi)


## initialize conc
P1 = FiniteElement('P', triangle, 1)
element = MixedElement([P1, P1, P1, P1])
V_c = FunctionSpace(mesh, element)

c_ruhex = 2 #mM
c_KCl = 100 #mM
# Note 1mM = 1mol/m3 (SI units)
c_a = Expression(str(c_KCl), degree=1)
c_b = Expression(str(z_1*c_KCl + z_3*c_ruhex), degree=1)
c_c = Expression(str(c_ruhex), degree=1)
c_d = Expression(str(0.0), degree=1)

q_1, q_2, q_3, q_4 = TestFunctions(V_c)
c = Function(V_c)
c_1, c_2, c_3, c_4 = split(c)


## BCs
tol = 1E-14
def boundary_1(x, on_boundary):
    return on_boundary and near(x[1], 0, tol)

def boundary_2(x, on_boundary):
    return on_boundary and near(x[0], 1e-7, tol)# and (x[1] < 1e-7))

def boundary_3(x, on_boundary):
    return on_boundary and (1e-7 < x[0] < 2e-7)

def boundary_4(x, on_boundary):
    return on_boundary and (2e-7 < x[0] < 3.5e-6)

def boundary_5(x, on_boundary):
    return on_boundary and near(x[1], 2e-5, tol)

# phi BCs
bc_1= DirichletBC(V_phi, phi_D, boundary_5)
bc_2= DirichletBC(V_phi, phi_L, boundary_1)
bcs_phi = [bc_1, bc_2] # All BCs are Neumann

# conc BCs
bc_5a= DirichletBC(V_c.sub(0), c_a, boundary_5)
bc_5b= DirichletBC(V_c.sub(1), c_b, boundary_5)
bc_5c= DirichletBC(V_c.sub(2), c_c, boundary_5)
bc_5d= DirichletBC(V_c.sub(3), c_d, boundary_5)
bcs_c = [bc_5a, bc_5b, bc_5c, bc_5d]

## Different Neumann BC for bottom BC
# create a mesh function which assigns an unsigned integer (size_t) to each edge
mf = MeshFunction("size_t", mesh, 1) # 3rd argument is dimension of an edge
mf.set_all(0) # initialize the function to zero
class BottomBoundary(SubDomain):
    def inside(self, x, on_boundary):
        return near(x[1], 0.0, tol) and on_boundary

bottomboundary = BottomBoundary() # instantiate it

# use this bottomboundary object to set values of the mesh function to 1 in the subdomain
bottomboundary.mark(mf, 1)

# define a new measure ds based on this mesh function
ds = Measure("ds", domain=mesh, subdomain_data=mf)
#ds = Measure("ds")(subdomain_data=mf)

### Compute solution
## Define problem for phi
r = Expression('x[0]', degree=1)
nabla_phi = (z_1*c_1 + z_2*c_2 + z_3*c_3 + z_4*c_4)
g = Expression('0.0', degree=1)
F_phi = (dot(grad(phi),grad(v)))*r*dx()
L_phi = (F/(eps*eps0))*nabla_phi*v*r*dx() + g*v*r*ds()
phi = Function(V_phi)
solve(F_phi == L_phi, phi, bcs_phi)

## Define problem for conc
r = Expression('x[0]', degree=1)
#f = Constant(0.0)
#g = Expression('-4*x[1]', degree=1)
g_1 = Expression('0.0', degree=1)
g_2 = Expression('0.0', degree=1)
g_3 = Expression('0.0', degree=1)
g_4 = Expression('0.0', degree=1)
n = FacetNormal(mesh)
#m1 = dot(grad(c_3), n)
#m1 = Dx(c_3,1) does not give correct solution
kox, kred = BV_rates(1e-3, -0.07, A=1.0, Vapp=Vapp_list[idx])
m1 = -(kred*c_3 - kox*c_4)/D_o # Rate theory input
m2 = dot(grad(c_4), n)
F_c = ((dot(grad(c_1), grad(q_1))) - ((z_1*a)*(dot(grad(c_1), grad(phi)))*q_1))*r*dx() \
    + ((dot(grad(c_2), grad(q_2))) - ((z_2*a)*(dot(grad(c_2), grad(phi)))*q_2))*r*dx() \
    + ((dot(grad(c_3), grad(q_3))) - ((z_3*a)*(dot(grad(c_3), grad(phi)))*q_3))*r*dx() \
    + ((dot(grad(c_4), grad(q_4))) - ((z_4*a)*(dot(grad(c_4), grad(phi)))*q_4))*r*dx() \
    + ((z_1*c_1*q_1 + z_2*c_2*q_2 + z_3*c_3*q_3 + z_4*c_4*q_4)*b*nabla_phi)*r*dx() \
    - g_1*q_1*r*ds() - g_2*q_2*r*ds() - g_3*q_3*r*ds(0) - g_4*q_4*r*ds(0) \
    - m1*q_3*r*ds(1) + (D_o/D_r)*m1*q_4*r*ds(1)

L_c = 0
c.vector()[:] = c_0
#c.vector()[:] = c_0.vector()[:]

solve(F_c == L_c, c, bcs_c)
_c_1, _c_2, _c_3, _c_4 = c.split()

c_0 = c.copy()
phi_0 = phi.copy()
#print(c.vector()[:])

# Finding optimal phi(z=0)
err_list = []
count = 1
error_L2 = 100

# phi solve initial
phi_D = Expression(str(0.0), degree=1)
phi_L = Expression(str(phi_z0), degree=1)
bc_1= DirichletBC(V_phi, phi_D, boundary_5)
bc_2= DirichletBC(V_phi, phi_L, boundary_1)
bcs_phi = [bc_1, bc_2] # All BCs are Neumann
    
phi_vec = phi_0.vector()[:].copy()
r = Expression('x[0]', degree=1)
nabla_phi = (z_1*c_1 + z_2*c_2 + z_3*c_3 + z_4*c_4)
g = Expression('0.0', degree=1)
F_phi = (dot(grad(phi),grad(v)))*r*dx() - (F/(eps*eps0))*nabla_phi*v*r*dx() - g*v*r*ds()
L_phi = 0
phi.vector()[:] = phi_0.vector()[:]
solve(F_phi == L_phi, phi, bcs_phi)
#print(errornorm(phi_0, phi, 'L2'),'\n')
err = norm(np.array(phi_0.vector()[:] - phi_vec))
print(count-1, err, '\n')
phi_0 = phi.copy()

#for j in range(20):
while err > 1e-12:    
    #phi.assign(phi_0)
    #c.assign(c_0)
    c_1, c_2, c_3, c_4 = split(c)

    g_1 = Expression('0.0', degree=1)
    g_2 = Expression('0.0', degree=1)
    g_3 = Expression('0.0', degree=1)
    g_4 = Expression('0.0', degree=1)
    n = FacetNormal(mesh)
    #m1 = dot(grad(c_3), n)
    #m1 = Dx(c_3,1) does not give correct solution
    kox, kred = BV_rates(1e-3, -0.07, A=1.0, Vapp=Vapp_list[16])
    m1 = -(kred*c_3 - kox*c_4)/D_o # Rate theory input
    m2 = dot(grad(c_4), n)
    F_c = ((dot(grad(c_1), grad(q_1))) - ((z_1*a)*(dot(grad(c_1), grad(phi)))*q_1))*r*dx() \
        + ((dot(grad(c_2), grad(q_2))) - ((z_2*a)*(dot(grad(c_2), grad(phi)))*q_2))*r*dx() \
        + ((dot(grad(c_3), grad(q_3))) - ((z_3*a)*(dot(grad(c_3), grad(phi)))*q_3))*r*dx() \
        + ((dot(grad(c_4), grad(q_4))) - ((z_4*a)*(dot(grad(c_4), grad(phi)))*q_4))*r*dx() \
        + ((z_1*c_1*q_1 + z_2*c_2*q_2 + z_3*c_3*q_3 + z_4*c_4*q_4)*b*nabla_phi)*r*dx() \
        - g_1*q_1*r*ds() - g_2*q_2*r*ds() - g_3*q_3*r*ds(0) - g_4*q_4*r*ds(0) \
        - m1*q_3*r*ds(1) + (D_o/D_r)*m1*q_4*r*ds(1)

    L_c = 0
    c.vector()[:] = c_0.vector()[:]
    solve(F_c == L_c, c, bcs_c)

    phi_vec = phi_0.vector()[:].copy()
    nabla_phi = (z_1*c_1 + z_2*c_2 + z_3*c_3 + z_4*c_4)
    g = Expression('0.0', degree=1)
    F_phi = (dot(grad(phi),grad(v)))*r*dx() - (F/(eps*eps0))*nabla_phi*v*r*dx() - g*v*r*ds()
    L_phi = 0
    phi.vector()[:] = phi_0.vector()[:]
    solve(F_phi == L_phi, phi, bcs_phi)
    err = norm(np.array(phi_0.vector()[:] - phi_vec))
    print(count, err, '\n')
    error_L2 = errornorm(phi_0, phi, 'L2')
    err_list.append(error_L2)
    
    #print(count, error_L2,'\n')
    c_0 = c.copy()
    phi_0 = phi.copy()
    count+=1
#plot(phi)

c_1, c_2, c_3, c_4 = split(c)
g_1 = Expression('0.0', degree=1)
g_2 = Expression('0.0', degree=1)
g_3 = Expression('0.0', degree=1)
g_4 = Expression('0.0', degree=1)
n = FacetNormal(mesh)
#m1 = dot(grad(c_3), n)
#m1 = Dx(c_3,1) does not give correct solution
kox, kred = BV_rates(1e-3, -0.07, A=1.0, Vapp=Vapp_list[idx])
m1 = -(kred*c_3 - kox*c_4)/D_o # Rate theory input
m2 = dot(grad(c_4), n)
F_c = ((dot(grad(c_1), grad(q_1))) - ((z_1*a)*(dot(grad(c_1), grad(phi)))*q_1))*r*dx() \
    + ((dot(grad(c_2), grad(q_2))) - ((z_2*a)*(dot(grad(c_2), grad(phi)))*q_2))*r*dx() \
    + ((dot(grad(c_3), grad(q_3))) - ((z_3*a)*(dot(grad(c_3), grad(phi)))*q_3))*r*dx() \
    + ((dot(grad(c_4), grad(q_4))) - ((z_4*a)*(dot(grad(c_4), grad(phi)))*q_4))*r*dx() \
    + ((z_1*c_1*q_1 + z_2*c_2*q_2 + z_3*c_3*q_3 + z_4*c_4*q_4)*b*nabla_phi)*r*dx() \
    - g_1*q_1*r*ds() - g_2*q_2*r*ds() - g_3*q_3*r*ds(0) - g_4*q_4*r*ds(0) \
    - m1*q_3*r*ds(1) + (D_o/D_r)*m1*q_4*r*ds(1)

L_c = 0
c.vector()[:] = c_0.vector()[:]
solve(F_c == L_c, c, bcs_c)

_c_1, _c_2, _c_3, _c_4 = c.split()
current = get_current(_c_3, mesh, a_s = 1e-7)
print(Vapp_list[idx], current)