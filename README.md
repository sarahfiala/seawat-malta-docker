# aquainfra_MaltaGW

## 🛠 Runtime Parameters

This container accepts the following command-line arguments at runtime:

| Parameter           | Description                                                                | Default Value             |
|---------------------|----------------------------------------------------------------------------|---------------------------|
| `--user_sealevels`  | List of sea level values (in metres) to simulate.                          | `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`  |
| `--sealevel_int`    | Interval duration in years between each sea level in the list.             | `1`                       |
| `--user_recharge`   | Recharge value used in the simulation.                                     | `0.00027`                 |


## Output:
The simulation output is saved to:
The output is found in: 
```
/out/salt_flow.nc
```


### 📌 Example Usage


How to build the docker image:

```bash
today=$(date '+%Y%m%d')
docker build -t maltagw:${today}
```

How to run the docker image:

```bash
mkdir ./results
docker run -it \
  -v "./results:/out:rw" \
  --name malta-container maltagw:${today} \
  --user_sealevels "[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]" \
  --sealevel_int 1 \
  --user_recharge 0.00027
```

You can also run without parameters. Then the model will pick the default values, which are defined in `SCRIPTS/setupSeaWAT.combined.py`:

```bash
docker run -it \
  -v "./results:/out:rw" \
  --name malta-container maltagw:${today}
```

