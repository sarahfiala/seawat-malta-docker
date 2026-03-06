#%% Import libraries
import os
import sys
import subprocess
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import colors
import flopy
import flopy.utils.binaryfile as bf
import xarray as xr
import pyvista as pv
#import PVGeo
import yaml
#import imod

# At the top of setup_model.py
import argparse
import ast


# get the arguments
def getArgs():
    parser = argparse.ArgumentParser(description="Setup Malta SEAWAT model")
    parser.add_argument(
        "--user_sealevels",
        type=str,
        default="[0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0,0.0, 0.0, 0.0]",
        help="List of sea levels",
    )
    parser.add_argument(
        "--sealevel_int",
        type=int,
        default=1,
        help="Interval duration in years, i.e., time between each sealevel in the list",
    )
    parser.add_argument("--user_recharge", type=float, default=0.00027, help="Recharge value")
    parser.add_argument("--Project_root", type=str, default="/app", help="Project root directory")
    return parser.parse_args()


def setupSeaWAT(user_sealevels, sealevel_int, user_recharge):
    #pass  # TODO: add function code here

    #%% Define directories and model name
    project_root = "/app"

    # Input, output, and model directories (relative to root)
    input_dir = os.path.join(project_root, 'example_inputs')
    output_dir = os.path.join(project_root, 'example_results')
    model_name = 'Malta_Model'
    model_dir = os.path.join(project_root, 'model_files', 'malta_simulation', model_name)

    # Define mini_sp_dir (SEAWAT working folder)
    mini_sp_dir = os.path.join(model_dir, 'malta_sp0', model_name)

    # Write ALL SEAWAT input files (and the namefile) here:
    #output_dir = mini_sp_dir

    # Executables
    #imod_path = os.path.join(project_root, 'model_files', 'bin', '_imodwq', '_imodwq', 'imod-wq_svn392_x64r.exe')
    #seawat_exe_dir = os.path.join(project_root, 'model_files', 'bin', 'SEAWAT', 'SEAWAT', 'swt_v4_00_05')
    seawat_exe_dir = os.path.join(project_root, 'SEAWAT', 'swt_v4.exe')
    modflow_exe_dir = os.path.join(project_root, 'SEAWAT', 'mf2005.exe')
    mt3d_exe_dir = os.path.join(project_root, 'SEAWAT', 'mt3dms.exe')

    #USER INPUTS

    # Create directories if they don't exist
    for path in [input_dir, output_dir, model_dir]:
        print(f"Creating directory {path}")
        os.makedirs(path, exist_ok=True)

    #%% Load and process geological data from Petrel-exported CSV

    # Define column names expected in the input file
    fields = ['I', 'J', 'K', 'X', 'Y', 'Z', 'fac', 'por', 'hyd']

    # Read CSV starting from the 11th line (skipping headers)
    df_in = pd.read_csv(
        os.path.join(input_dir, "petrel_data"),
        skiprows=11,
        sep=r"\s+",
        engine="python",
        names=fields,
        header=None,
        index_col=False
    )

    # Round values to appropriate precision
    df_in[['I', 'J', 'K']] = df_in[['I', 'J', 'K']].round(0)
    df_in[['Z', 'fac', 'por', 'hyd']] = df_in[['Z', 'fac', 'por', 'hyd']].round(1)

    #%% Generate model grid dimensions from the data

    dx = dy = 200  # Horizontal cell size (in meters)
    dz = 20        # Vertical layer thickness

    # Extract unique layer, row, and column indices
    lay_arr = np.unique(df_in.K.values)
    row_arr = np.unique(df_in.I.values)
    col_arr = np.unique(df_in.J.values)

    # Initialize IBOUND array (used to define active/inactive cells)
    full_ibound_arr = np.zeros((lay_arr.shape[0], row_arr.shape[0], col_arr.shape[0]))

    # Extract top and bottom elevations from unique Z values
    z_vals = np.unique(df_in.Z.values)
    top_elev = np.nanmax(z_vals)
    bot_elev = np.arange(top_elev, np.nanmin(z_vals) - 2 * dz, -dz)[1:]

    # Print model grid info
    print(f"Top elevation: {top_elev} m bsl")
    print(f"Bottom elevation: {bot_elev[-1]} m bsl")
    print(f"Number of layers: {full_ibound_arr.shape[0]}")
    print(f"Rows: {full_ibound_arr.shape[1]}, Columns: {full_ibound_arr.shape[2]}")

    #%% Define sea level changes and stress periods

    # Sea levels (one for each stress period)
    sp_sealevel = user_sealevels  # THis will be a user input

    # Create names for each stress period
    sp_names = [f"malta_sp{i}" for i in range(len(sp_sealevel))]
    sealevel_int = sealevel_int  # This will be a user input in years

    # Duration of each stress period (in years)
    sp_time = sealevel_int * np.ones_like(sp_sealevel)

    # Select the first stress period
    a = 0
    model_name_sp = sp_names[a]
    sp_dir = os.path.join(model_dir, model_name_sp)
    os.makedirs(sp_dir, exist_ok=True)

    # Define time bounds for this mini-model run
    time_start = 0
    time_end = len(sp_sealevel) * sealevel_int
    #mini_modelname = f'SP_{time_start}_to_{time_end}'
    mini_modelname = "Malta_Model"
    mini_sp_dir = os.path.join(sp_dir, mini_modelname)

    # Create SEAWAT model object
    #flopy.modflow.Modflow.set_exe_path(modflow_exe_dir)
    #flopy.mt3d.Mt3dms.set_exe_path(mt3d_exe_dir)
    #flopy.seawat.Seawat.set_exe_path(seawat_exe_dir)
    mswt = flopy.seawat.Seawat(mini_modelname, 'nam_swt', model_ws=mini_sp_dir, exe_name=seawat_exe_dir)

    #%% Fill in hydraulic conductivity, porosity, and IBOUND arrays

    # Initialize property arrays with shape of the model grid
    ibound_arr = np.copy(full_ibound_arr)
    hk_arr = np.copy(full_ibound_arr)
    poro_arr = np.copy(full_ibound_arr)

    # Filter only the cells with positive facies value
    df_sel = df_in[df_in['fac'] > 0]

    # Loop through each row and fill in the model arrays
    for _, row in df_sel.iterrows():
        k, i, j = int(row['K']) - 1, int(row['I']) - 1, int(row['J']) - 1
        hk_arr[k, i, j] = row['hyd']
        poro_arr[k, i, j] = row['por']
        ibound_arr[k, i, j] = 1  # Active cell

    #%% Define starting heads (strt_arr) and concentrations (init_conc_arr) CHANGED FROM sconc_arr and strt_arr
    file_path = os.path.join(input_dir, "initial_equilibrium_state")
    #file_path="PATH TO/initial_equilibrium_state"
    df = pd.read_csv(file_path, skiprows=1, header=None)
    df.columns = ["X", "Y", "Z", "HEAD", "CONC", "VX", "VY", "VZ"]

    init_head = df["HEAD"].values
    nlay = 33
    ncol = 255
    nrow = 135
    init_head_arr = np.reshape(init_head, (nlay, ncol, nrow))

    init_conc = df["CONC"].values
    init_conc_arr = np.reshape(init_conc, (nlay, ncol, nrow))
    mask = np.isclose(init_conc_arr, 1e+30, rtol=1e-5)
    init_conc_arr = init_conc_arr.astype(np.float64)  # ensure we can store np.nan

    #Starting arrays for future projections
    init_conc_arr[mask] = np.nan
    init_head_arr = np.array(init_head_arr, copy=True)
    init_head_arr[init_head_arr == -999.99] = 0

    # Creating initial Chloride
    init_chlor_arr = np.zeros((nlay, ncol, nrow))
    init_chlor_arr[15:25, 80:90, 45:55] = 2500
    init_chlor_arr[3:10, 115:120, 99:106] = 2500

    # Ensure arrays are valid
    init_conc_arr = np.array(init_conc_arr, dtype=np.float32)
    init_chlor_arr = np.array(init_chlor_arr, dtype=np.float32)

    # Confirm shapes match
    assert init_conc_arr.shape == init_chlor_arr.shape == (33, 255, 135)

    # Pass as list of arrays
    sconc_arr = [init_conc_arr, init_chlor_arr]
    #print(sconc_arr.shape)

    #sconc_arr = ibound_arr * 35.  # Starting concentration (35 TDS mg/l)
    #TODO put the init_conc_arr for salt

    #strt_arr = ibound_arr * 0  # Starting head (0 m)
    #TODO put the init_head_arr
    #TDOD add the init_chlor_arr for you chloride

    #%%  DIS Package - Fixed Order

    # Define number of layers, rows, columns, and grid cell sizes
    nlay = lay_arr.shape[0]
    nrow = row_arr.shape[0]
    ncol = col_arr.shape[0]
    delr = dx  # Horizontal cell size
    delc = dy  # Horizontal cell size

    # Define the number of stress periods (should be defined based on sp_sealevel length)
    nper = len(sp_sealevel)  # Number of stress periods

    # Define stress period parameters
    perlen = np.full(nper, 365.25 * sealevel_int)  # Array filled with 500 years in days for each stress period
    nstp = np.full(nper, 12)  # Number of time steps per stress period

    # Create the DIS package using Flopy
    dis = flopy.modflow.ModflowDis(
        mswt,
        nlay,
        nrow,
        ncol,
        nper=nper,
        delr=delr,
        delc=delc,
        top=top_elev,
        botm=bot_elev,
        perlen=perlen,
        nstp=nstp
    )

    #%% Verifying 30 year period
    print("nper:", nper)
    print("perlen[0]:", perlen[0], "count:", len(perlen))

    #%% BAS Package
    bas = flopy.modflow.ModflowBas(mswt, ibound=ibound_arr, strt=init_head_arr)  #CHANGED FROM strt = strt_arr to init = init_conc_arr

    #%% LPF Package Flow Solver (PCG Package)
    pcg = flopy.modflow.ModflowPcg(
        mswt,
        hclose=1e-6,
        rclose=1e-3,
        mxiter=100,
        iter1=100,
        npcond=1,
        relax=0.98
    )

    # setting anisotropy to the hyd. conductivity field
    vk_arr = hk_arr * 0.1
    lpf = flopy.modflow.ModflowLpf(mswt, laytyp=0, hk=hk_arr, vka=vk_arr, ipakcb=1)

    #%% BOUNDARY CONDITIONS

    # Copy ibound array for MT3DMS boundary usage
    icbund_arr = ibound_arr.copy()

    # Initialize input containers
    ghb_input_all = []
    ssmdata_all = []

    # Get SSM itype dictionary
    itype = flopy.mt3d.Mt3dSsm.itype_dict()

    # Loop over each stress period
    for a, sea_level in enumerate(sp_sealevel):

        ghb_input_lst = []
        ssmdata = []

        # Inland boundaries (edges of the domain, above sea level)
        row_edges = [0, nrow - 1]
        for i in range(ncol):
            for row in row_edges:
                col_cells = ibound_arr[:, row, i]
                if 1 in col_cells:
                    lay_idx = col_cells.tolist().index(1)
                    if bot_elev[lay_idx] + dz >= sea_level:
                        for k in range(nlay):
                            if bot_elev[k] + dz >= sea_level:
                                cond_val = hk_arr[k, row, i] * dz * 1000
                                ghb_input_lst.append([k, row, i, bot_elev[k] + dz, cond_val])
                                ssmdata.append([k, row, i, 0.0, itype['GHB'], 1, 2])
                                icbund_arr[k, row, i] = -1  # mark as GHB cell for MT3DMS

        # Offshore domain (top layer only, below sea level)
        for i in range(nrow):
            for j in range(ncol):
                col_cells = ibound_arr[:, i, j]
                if 1 in col_cells:
                    lay_idx = col_cells.tolist().index(1)
                    if bot_elev[lay_idx] + dz < sea_level:
                        cond_val = (vk_arr[lay_idx, i, j] * delc * delr) / dz
                        ghb_input_lst.append([lay_idx, i, j, sea_level, cond_val])
                        ssmdata.append([lay_idx, i, j, 35.0, itype['GHB'], 1, 2])

        # Store stress period data
        ghb_input_all.append(ghb_input_lst)
        ssmdata_all.append(ssmdata)

    # Format GHB input for stress periods
    ghb_arr_in = {
        d: [list(entry) for entry in ghb_input_all[d]] if ghb_input_all[d] else []
        for d in range(len(ghb_input_all))
    }

    # Format SSM input
    ssm_arr_in = {
        e: ssmdata_all[e]
        for e in range(len(ssmdata_all))
    }

    # Create GHB Package
    ghb = flopy.modflow.ModflowGhb(
        mswt,
        ipakcb=1,
        stress_period_data=ghb_arr_in
    )

    #%% RCH & DRN Package

    rch_val = user_recharge

    # Create a 2D recharge array (for a single stress period)
    rch_arr = np.zeros((ibound_arr.shape[1], ibound_arr.shape[2]))
    drn_input_lst = []

    # Apply recharge and define drains only for the top active cell in each column
    for i in range(ibound_arr.shape[1]):
        for j in range(ibound_arr.shape[2]):
            lay_lst = [t for t in ibound_arr[:, i, j].tolist() if t == 1]
            if len(lay_lst) > 0:
                top_act_lay = ibound_arr[:, i, j].tolist().index(1)
                top_act_elev = top_elev - top_act_lay * dz

                # If top active elevation is above sea level
                if top_act_elev >= sea_level:
                    # Assign recharge
                    rch_arr[i, j] = rch_val

                    # Assign drain
                    cond_cell = (vk_arr[top_act_lay, i, j] * dx * dy) / dz
                    drn_input_lst.append([int(top_act_lay), i, j, top_act_elev, cond_cell])

    # Build recharge dictionary for each stress period
    rch_arr_in = {}
    for c in range(len(perlen)):
        rch_arr_in[c] = rch_arr

    # Define RCH package
    rch = flopy.modflow.ModflowRch(mswt, nrchop=3, ipakcb=1, rech=rch_arr_in)

    # Define DRN package if applicable
    if len(drn_input_lst) > 0:
        drn_arr_in = {}
        for c in range(len(perlen)):
            drn_arr_in[c] = drn_input_lst
        drn = flopy.modflow.ModflowDrn(mswt, ipakcb=1, stress_period_data=drn_arr_in)

    #%% Output Control
    ihedfm = 1
    iddnfm = 0
    extension = ['oc', 'hds', 'ddn', 'cbc']
    unitnumber = [14, 30, 52, 51]

    # Output control settings
    spd = {}
    for t in range(nper):
        spd[(t, nstp[t] - 1)] = ['SAVE HEAD', 'SAVE BUDGET', 'PRINT HEAD', 'PRINT BUDGET']

    oc = flopy.modflow.ModflowOc(
        mswt,
        ihedfm=ihedfm,
        stress_period_data=spd,
        unitnumber=unitnumber,
        compact=True
    )

    #%% BTN Package
    #   the BTN package
    porosity = poro_arr
    dt0 = 1000
    ifmtcn = 0
    chkmas = False
    nprmas = 10
    nprobs = 10
    total_sim_time = sum(perlen)
    #timprs_lst = list(np.linspace(1,total_sim_time,(nper-1),endpoint=True,dtype=int))
    timprs_lst = np.cumsum(perlen).tolist()

    btn = flopy.mt3d.Mt3dBtn(
        model=mswt,
        prsity=porosity,
        sconc=init_conc_arr,
        sconc2=init_chlor_arr,
        nper=nper,  # ✅ REQUIRED: number of stress periods
        ncomp=2,
        mcomp=2,
        #nprs=nprs,
        #timprs=timprs_1st,
        ifmtcn=ifmtcn,
        chkmas=chkmas,
        nprobs=nprobs,
        nprmas=nprmas
    )

    #btn = flopy.mt3d.Mt3dBtn(mswt, nprs=nprs, timprs=timprs_lst, prsity=porosity, init_conc=init_conc_arr,
    #                         ifmtcn=ifmtcn, chkmas=chkmas, nprobs=nprobs, nprmas=nprmas,dt0=1000)

    gcg = flopy.mt3d.Mt3dGcg(
        model=mswt,
        mxiter=1,     # number of outer iterations (1 is typical for SEAWAT)
        iter1=50,     # number of inner iterations
        isolve=3,     # solver type: 3 = BiCGSTAB (recommended)
        cclose=1e-6,  # convergence criterion
        iprgcg=0      # print option
    )

    #%% ADV Package
    adv = flopy.mt3d.Mt3dAdv(mswt, mixelm=0, mxpart=2000000)

    #%% DSP Package
    dmcoef_salt = 1.2e-10 * np.ones_like(ibound_arr)
    dmcoef_chlor = 5e-11 * np.ones_like(ibound_arr)
    # effective molecular diffusion coefficient [M2/D]
    al = 1.   # longitudinal dispersivity (L)
    trpt = 10  # transverse dispersivity for the cell in the x-direction (L)
    trpv = 10  # transverse dispersivity for the cell in the z-direction (L)

    dsp = flopy.mt3d.Mt3dDsp(
        mswt,
        al=al,
        trpt=trpt,
        trpv=trpv,
        multiDiff=True,
        dmcoef=dmcoef_salt,
        dmcoef2=dmcoef_chlor
    )

    #%% VDF Package
    iwtable = 0     # Flag for the table of densities (if using a density table or not)
    densemin = 1000.  # Minimum density (typically freshwater in kg/m^3)
    densemax = 1025.  # Maximum density (typically saline water in kg/m^3)
    denseref = 1000.  # Reference density for freshwater
    denseslp = 0.7143 # Slope of the density function for solute concentration (typically for seawater)
    firstdt = 0.001   # First timestep in days

    vdf = flopy.seawat.SeawatVdf(
        mswt,
        iwtable=iwtable,
        densemin=densemin,
        densemax=densemax,
        denseref=denseref,
        denseslp=denseslp,
        firstdt=firstdt
    )

    #%% SSM Package
    #   write the SSM package
    ssm_arrs = {}
    for c in range(nper):
        ssm_arrs[c] = np.copy(rch_arr_in[c]) * 0.0  # Recharge array, all set to 0

    #ssm_rch_in_2d = ssm_rch_in.reshape(nrow, ncol)  # Reshape to 2D (255 x 135)
    # Now broadcast to match the shape for all stress periods (nper, nrow * ncol)
    #ssm_rch_all = np.broadcast_to(ssm_rch_in_2d, (nper, nrow, ncol))  # Shape (nper, 255, 135)

    # Define the SSM package with the reshaped array for recharge
    ssm = flopy.mt3d.Mt3dSsm(mswt, crch=ssm_arrs[0], stress_period_data=ssm_arr_in)

    #%% Write simulation
    mswt.write_input()

    #%% Writing files
    # Write the ascii file with vertical sum of active cells in IBOUND
    full_ibound_arr = np.sum(ibound_arr, axis=0, dtype=np.int32)  # This is your 2D array (255, 135)

    # Convert the 2D array to a string (join all rows together into one string)
    full_ibound_arr_str = '\n'.join(' '.join(map(str, row)) for row in full_ibound_arr)

    # Open the file in binary mode ('wb') to write the string as bytes (same as original behavior)
    with open(os.path.join(mini_sp_dir, 'LOAD.ASC'), 'wb') as f:
        f.write(full_ibound_arr_str.encode('utf-8'))  # Encode the string into bytes before writing

    # Create the pksf and pkst files - change it in case the grid discretization changes
    pksf_lines = [
        'ISOLVER 1', 'NPC 2', 'MXITER 1500', 'RELAX .98', 'HCLOSEPKS 0.05', 'RCLOSEPKS 20000.0', 'PARTOPT 0',
        'PARTDATA', 'external 40 1. (free) -1',
        'GNCOL {}'.format(ncol), 'GNROW {}'.format(nrow),
        'GDELR', '{}'.format(dx), 'GDELC', '{}'.format(dy),  # Correct GDELC to use 'dy' for the vertical dimension
        'NOVLAPADV 2', 'END'
    ]

    pkst_lines = [
        'ISOLVER 2', 'NPC 2', 'MXITER 1500', 'INNERIT 200', 'RELAX .98', 'RCLOSEPKS 1.0E-01',
        'HCLOSEPKS 1.0E+12', 'RELATIVE-L2NORM', 'END'
    ]

    # Write pksf file
    with open(os.path.join(mini_sp_dir, mini_modelname + '.pksf'), 'w') as f:
        for line in pksf_lines:
            f.write(line)
            f.write('\n')

    # Write pkst file
    with open(os.path.join(mini_sp_dir, mini_modelname + '.pkst'), 'w') as f:
        for line in pkst_lines:
            f.write(line)
            f.write('\n')

    # Open the nam_swt file and append these three lines
    nam_lines = [
        '#PKSF 27 ' + mini_modelname + '.pksf',
        '#PKST 35 ' + mini_modelname + '.pkst',
        'DATA 40 LOAD.ASC',
        '#DATA(BINARY) 1 ' + mini_modelname + '.cbc',
        '#DATA(BINARY) 30 ' + mini_modelname + '.hds',
        'DATA(BINARY) 50 ' + mini_modelname + '.ucn'
    ]

    with open(os.path.join(mini_sp_dir, mini_modelname + '.nam_swt'), 'a') as f:
        for line in nam_lines:
            f.write(line)
            f.write('\n')

    # Save the ibound_arr (if it doesn't exist)
    ibound_arr_dir = os.path.join(mini_sp_dir, 'ibound_arr.npy')
    if not os.path.isfile(ibound_arr_dir):
        np.save(ibound_arr_dir, ibound_arr)


#MAIN FUNCTION
def main():
    args = getArgs()

    # Convert sea levels string to list
    user_sealevels = ast.literal_eval(args.user_sealevels)
    sealevel_int = args.sealevel_int
    user_recharge = args.user_recharge

    setupSeaWAT(user_sealevels, sealevel_int, user_recharge)


if __name__ == "__main__":
    main()
