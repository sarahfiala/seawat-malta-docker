#!/bin/bash
set -euo pipefail

BASEDIR="/app"
SEAWATEXE="${BASEDIR}/SEAWAT/swt_v4.exe"

MOD_DIR="${BASEDIR}/model_files/malta_simulation/Malta_Model/malta_sp0/Malta_Model"
NAMFILE="Malta_Model.nam_swt"

SCRIPTS_DIR="${BASEDIR}/SCRIPTS"
SETUP_PY="${SCRIPTS_DIR}/setupSeaWAT.combined.py"
CONVERT_PY="${SCRIPTS_DIR}/convertSeaWatOutputToNC.py"

OUTDIR="/out"
if [ ! -d "$OUTDIR" ]; then
  OUTDIR="${BASEDIR}/example_results"
fi
mkdir -p "$OUTDIR" "$OUTDIR/logs"

echo "=========================================="
echo "SEAWAT run script starting"
echo "Model dir:   $MOD_DIR"
echo "Output dir:  $OUTDIR"
echo "=========================================="

USER_SEALEVELS="${USER_SEALEVELS:-[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0]}"
SEALEVEL_INT="${SEALEVEL_INT:-1}"
USER_RECHARGE="${USER_RECHARGE:-0.00027}"

# ---------- Check scripts ----------
if [ ! -f "$SETUP_PY" ]; then
  echo "❌ Missing setup script: $SETUP_PY"
  exit 1
fi

if [ ! -f "$CONVERT_PY" ]; then
  echo "❌ Missing conversion script: $CONVERT_PY"
  exit 1
fi

# ---------- Ensure required inputs exist ----------
if [ ! -f "${BASEDIR}/example_inputs/petrel_data.gz" ] && [ ! -f "${BASEDIR}/example_inputs/petrel_data" ]; then
  echo "❌ Missing petrel input."
  ls -lh "${BASEDIR}/example_inputs" || true
  exit 1
fi

if [ ! -f "${BASEDIR}/example_inputs/initial_equilibrium_state.gz" ] && [ ! -f "${BASEDIR}/example_inputs/initial_equilibrium_state" ]; then
  echo "❌ Missing initial equilibrium input."
  ls -lh "${BASEDIR}/example_inputs" || true
  exit 1
fi

# ---------- Decompress .gz if needed ----------
if [ -f "${BASEDIR}/example_inputs/petrel_data.gz" ] && [ ! -f "${BASEDIR}/example_inputs/petrel_data" ]; then
  echo "Decompressing petrel_data.gz ..."
  gunzip -c "${BASEDIR}/example_inputs/petrel_data.gz" > "${BASEDIR}/example_inputs/petrel_data"
fi

if [ -f "${BASEDIR}/example_inputs/initial_equilibrium_state.gz" ] && [ ! -f "${BASEDIR}/example_inputs/initial_equilibrium_state" ]; then
  echo "Decompressing initial_equilibrium_state.gz ..."
  gunzip -c "${BASEDIR}/example_inputs/initial_equilibrium_state.gz" > "${BASEDIR}/example_inputs/initial_equilibrium_state"
fi

test -s "${BASEDIR}/example_inputs/petrel_data"
test -s "${BASEDIR}/example_inputs/initial_equilibrium_state"

# ---------- Clear previous run ----------
mkdir -p "${MOD_DIR}"
rm -rf "${MOD_DIR:?}/"*

# ---------- Run Python setup ----------
echo "Running setupSeaWAT..."
python3 "$SETUP_PY" \
  --user_sealevels "${USER_SEALEVELS}" \
  --sealevel_int "${SEALEVEL_INT}" \
  --user_recharge "${USER_RECHARGE}" \
  --Project_root "${BASEDIR}"

echo "Setup complete."
ls -lh "${MOD_DIR}" || true

# ---------- Run SEAWAT ----------
echo "Running SEAWAT..."
cd "${MOD_DIR}"

export WINEDEBUG="-all"
export WINEDLLOVERRIDES="mscoree,mshtml="

SEAWAT_LOG="${OUTDIR}/logs/seawat_stdout.log"

if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a wine "${SEAWATEXE}" "${NAMFILE}" 2>&1 | tee "${SEAWAT_LOG}"
  SEAWAT_EXIT=${PIPESTATUS[0]}
else
  wine "${SEAWATEXE}" "${NAMFILE}" 2>&1 | tee "${SEAWAT_LOG}"
  SEAWAT_EXIT=${PIPESTATUS[0]}
fi

cd - >/dev/null

if [ $SEAWAT_EXIT -ne 0 ]; then
  echo "❌ SEAWAT failed. See log:"
  tail -n 100 "${SEAWAT_LOG}"
  exit 1
fi

echo "SEAWAT finished successfully."

# ---------- Check outputs ----------
for f in \
  "${MOD_DIR}/MT3D001.UCN" \
  "${MOD_DIR}/MT3D002.UCN" \
  "${MOD_DIR}/Malta_Model.hds" \
  "${MOD_DIR}/Malta_Model.cbc" \
  "${MOD_DIR}/Malta_Model.dis"
do
  if [ ! -s "$f" ]; then
    echo "❌ Missing or empty output: $f"
    exit 1
  fi
done

echo "All expected SEAWAT outputs found."

# ---------- Convert to NetCDF ----------
echo "Converting to salt_chlor.nc..."
python3 "$CONVERT_PY" \
  --dis "${MOD_DIR}/Malta_Model.dis" \
  --hds "${MOD_DIR}/Malta_Model.hds" \
  --cbc "${MOD_DIR}/Malta_Model.cbc" \
  --ucn-salt "${MOD_DIR}/MT3D001.UCN" \
  --ucn-chlor "${MOD_DIR}/MT3D002.UCN" \
  --output "${OUTDIR}/salt_chlor.nc"

echo "=========================================="
echo "SUCCESS"
echo "NetCDF created at:"
echo "${OUTDIR}/salt_chlor.nc"
echo "=========================================="
