#!/usr/bin/env python3
import argparse
import os
import numpy as np
import xarray as xr
import flopy
import flopy.utils.binaryfile as bf


def load_dis_dims(dis_path):
    model_ws = os.path.dirname(dis_path)
    dis_file = os.path.basename(dis_path)
    modelname = os.path.splitext(dis_file)[0]

    mf = flopy.modflow.Modflow(modelname=modelname, model_ws=model_ws)

    original_cwd = os.getcwd()
    try:
        os.chdir(model_ws)
        dis = flopy.modflow.ModflowDis.load(dis_file, model=mf)
        nlay, nrow, ncol = int(dis.nlay), int(dis.nrow), int(dis.ncol)
        print(f"✅ DIS dims: nlay={nlay}, nrow={nrow}, ncol={ncol}")
        return nlay, nrow, ncol
    finally:
        os.chdir(original_cwd)


def load_ucn_last(ucn_path):
    ucn = bf.UcnFile(ucn_path)
    times = ucn.get_times()
    if not times:
        raise RuntimeError(f"No times found in {ucn_path}")
    tsel = float(times[-1])
    arr = np.asarray(ucn.get_data(totim=tsel), dtype=np.float32)  # (nlay,nrow,ncol)
    print(f"✅ UCN {os.path.basename(ucn_path)} at time={tsel} shape={arr.shape}")
    return arr, tsel


def load_hds_last(hds_path, tsel):
    hds = bf.HeadFile(hds_path)
    arr = np.asarray(hds.get_data(totim=tsel), dtype=np.float32)  # (nlay,nrow,ncol)
    print(f"✅ HDS at time={tsel} shape={arr.shape}")
    return arr


def _cbc_extract_array(a):
    if isinstance(a, list):
        return a[0] if len(a) > 0 else None
    return a


def load_cbc_last(cbc_path, tsel):
    cbc = bf.CellBudgetFile(cbc_path)

    def get_one(labels):
        for lab in labels:
            try:
                a = cbc.get_data(text=lab, totim=tsel)
                a = _cbc_extract_array(a)
                if a is not None:
                    return np.asarray(a, dtype=np.float32)
            except Exception:
                continue
        return None

    vx = get_one(["FLOW RIGHT FACE", "FLOW RIGHT FACE "])
    vy = get_one(["FLOW FRONT FACE", "FLOW FRONT FACE "])
    vz = get_one(["FLOW LOWER FACE", "FLOW LOWER FACE "])

    if vx is None or vy is None or vz is None:
        raise RuntimeError("Could not read FLOW RIGHT/FRONT/LOWER FACE from CBC.")

    print(f"✅ CBC face flows at time={tsel} shape={vx.shape}")
    return vx, vy, vz


def clean_fill_values(arr, name):
    """
    Only mask obvious SEAWAT/MT3D fill values.
    Do not apply min/max clipping here.
    """
    out = np.asarray(arr, dtype=np.float32).copy()

    high_fill = int((out > 1e20).sum())
    low_fill = int((out < -1e20).sum())

    out[out > 1e20] = np.nan
    out[out < -1e20] = np.nan

    finite = int(np.isfinite(out).sum())
    print(f"🧹 {name}: masked fill high={high_fill}, low={low_fill}, finite={finite}")
    return out


def save_snapshot_combined(
    conc_salt,
    conc_chlor,
    head,
    vx,
    vy,
    vz,
    tsel,
    nlay,
    nrow,
    ncol,
    output_path,
):
    # legacy-style 1-based indices so Panoply behaves like the old file
    k = np.arange(1, nlay + 1, dtype=np.int32)
    j = np.arange(1, nrow + 1, dtype=np.int32)
    i = np.arange(1, ncol + 1, dtype=np.int32)

    ds = xr.Dataset(
        data_vars={
            "CONC_SALT": (("k", "j", "i"), conc_salt),
            "CONC_CHLOR": (("k", "j", "i"), conc_chlor),
            "HEAD": (("k", "j", "i"), head),
            "VX": (("k", "j", "i"), vx),
            "VY": (("k", "j", "i"), vy),
            "VZ": (("k", "j", "i"), vz),
        },
        coords={
            "k": ("k", k),
            "j": ("j", j),
            "i": ("i", i),
            "Z": ("k", k),
            "Y": ("j", j),
            "X": ("i", i),
            "time": ("time", np.array([tsel], dtype=np.float32)),
        },
        attrs={
            "title": "SEAWAT combined output snapshot",
            "description": "Combined salinity, chloride, head, and face-flow snapshot from SEAWAT outputs",
            "totim": tsel,
            "note": "X,Y,Z are 1-based indices to mimic legacy combined concvelo-style output.",
        },
    )

    ds["CONC_SALT"].attrs["units"] = "mg/L"
    ds["CONC_SALT"].attrs["long_name"] = "salt concentration"

    ds["CONC_CHLOR"].attrs["units"] = "mg/L"
    ds["CONC_CHLOR"].attrs["long_name"] = "chloride concentration"

    ds["HEAD"].attrs["long_name"] = "head"

    ds["VX"].attrs["long_name"] = "flow right face"
    ds["VY"].attrs["long_name"] = "flow front face"
    ds["VZ"].attrs["long_name"] = "flow lower face"

    encoding = {
        "CONC_SALT": {"_FillValue": np.float32(np.nan)},
        "CONC_CHLOR": {"_FillValue": np.float32(np.nan)},
        "HEAD": {"_FillValue": np.float32(np.nan)},
        "VX": {"_FillValue": np.float32(np.nan)},
        "VY": {"_FillValue": np.float32(np.nan)},
        "VZ": {"_FillValue": np.float32(np.nan)},
    }

    ds.to_netcdf(output_path, encoding=encoding)
    print(f"✅ NetCDF saved: {output_path}")


def main():
    p = argparse.ArgumentParser(
        description="Convert SEAWAT UCN + HDS + CBC files to a combined NetCDF snapshot."
    )
    p.add_argument("--dis", required=True, help="Path to Malta_Model.dis")
    p.add_argument("--hds", required=True, help="Path to Malta_Model.hds")
    p.add_argument("--cbc", required=True, help="Path to Malta_Model.cbc")
    p.add_argument("--ucn-salt", required=True, help="Path to MT3D001.UCN")
    p.add_argument("--ucn-chlor", required=True, help="Path to MT3D002.UCN")
    p.add_argument("--output", default="salt_chlor.nc", help="Output NetCDF path")
    args = p.parse_args()

    for fp in [args.dis, args.hds, args.cbc, args.ucn_salt, args.ucn_chlor]:
        if not os.path.isfile(fp):
            raise FileNotFoundError(f"File not found: {fp}")

    nlay, nrow, ncol = load_dis_dims(args.dis)

    conc_salt, tsel1 = load_ucn_last(args.ucn_salt)
    conc_chlor, tsel2 = load_ucn_last(args.ucn_chlor)

    if conc_salt.shape != (nlay, nrow, ncol):
        raise ValueError(f"Salt shape {conc_salt.shape} does not match DIS dims {(nlay, nrow, ncol)}")
    if conc_chlor.shape != (nlay, nrow, ncol):
        raise ValueError(f"Chloride shape {conc_chlor.shape} does not match DIS dims {(nlay, nrow, ncol)}")

    if abs(tsel1 - tsel2) > 1e-6:
        print(f"⚠️ Warning: salt/chlor times differ ({tsel1} vs {tsel2}). Using salt time.")

    tsel = tsel1

    head = load_hds_last(args.hds, tsel)
    vx, vy, vz = load_cbc_last(args.cbc, tsel)

    if head.shape != (nlay, nrow, ncol):
        raise ValueError(f"HDS shape {head.shape} does not match DIS dims {(nlay, nrow, ncol)}")
    for name, arr in [("VX", vx), ("VY", vy), ("VZ", vz)]:
        if arr.shape != (nlay, nrow, ncol):
            raise ValueError(f"{name} shape {arr.shape} does not match DIS dims {(nlay, nrow, ncol)}")

    conc_salt = clean_fill_values(conc_salt, "CONC_SALT")
    conc_chlor = clean_fill_values(conc_chlor, "CONC_CHLOR")
    head = clean_fill_values(head, "HEAD")
    vx = clean_fill_values(vx, "VX")
    vy = clean_fill_values(vy, "VY")
    vz = clean_fill_values(vz, "VZ")

    save_snapshot_combined(
        conc_salt=conc_salt,
        conc_chlor=conc_chlor,
        head=head,
        vx=vx,
        vy=vy,
        vz=vz,
        tsel=tsel,
        nlay=nlay,
        nrow=nrow,
        ncol=ncol,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
