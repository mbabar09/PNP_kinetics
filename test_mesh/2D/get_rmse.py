from dragonfly import load_config_file, maximise_function
from argparse import Namespace
import numpy as np
import pickle, os, re, sys
import time, math
from pexpect.exceptions import TIMEOUT
from funcs_pnp import *
import matplotlib.pyplot as plt
import matplotlib as mpl
from optimize import analytical_model
import yaml

def loss_error(run_dir):
	iv_file = run_dir+'iv_data.txt'
	iv_data = np.loadtxt(iv_file, skiprows=1)
	
	argids = np.argsort(iv_data[:,1])
	Vapp_list = iv_data[:,1][argids]
	I = iv_data[:,0][argids]
	y_predicted = I/np.abs(I[0])
	y_actual = analytical_model(Vapp_list)
	MSE = np.square(np.subtract(y_actual,y_predicted)).mean() 
	RMSE = math.sqrt(MSE)
	return -RMSE

run_dir = sys.argv[1]
if run_dir[-1] != '/':
    run_dir+='/'
    
print(loss_error(run_dir))
