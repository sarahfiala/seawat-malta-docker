#!/bin/sh
cd /app/SCRIPTS
echo "Running runSeaWat.sh with arguments: $@"
"/app/SCRIPTS/runSeaWat.sh" "$@"


# In Dockerfile, it was:
#WORKDIR /app/SCRIPTS
#CMD ["bash", "./run_model.sh"]
