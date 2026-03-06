import os
import json
import requests
import shutil
import subprocess
import logging
LOGGER = logging.getLogger(__name__)

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError
from pygeoapi.process.aquainfra_MaltaGW.pygeoapi_processes.utils import log_docker_output
from pygeoapi.process.aquainfra_MaltaGW.pygeoapi_processes.utils import get_error_message_from_docker_stderr

'''

# To run the model with the values provided by the user
curl -i -X POST "https://${PYSERVER}/processes/malta-groundwater/execution" \
--header "Content-Type: application/json" \
--header "Prefer: respond-async" \
--data '{
  "inputs": {
    "sealevel_int": 250,
    "user_recharge": 0.002,
    "user_sealevels": [-3.0, -2.0, -1.0]
  }
}'

# To run the model with the default values defined in the containe# To run the model with the default values defined in the container
curl -i -X POST "https://${PYSERVER}/processes/malta-groundwater/execution" \
--header "Content-Type: application/json" \
--header "Prefer: respond-async" \
--data '{
  "inputs": {}
}'

'''

LOGGER = logging.getLogger(__name__)

# Process metadata and description
# Has to be in a JSON file of the same name, in the same dir! 
script_title_and_path = __file__
metadata_title_and_path = script_title_and_path.replace('.py', '.json')
PROCESS_METADATA = json.load(open(metadata_title_and_path))

class MaltaGroundwaterProcessor(BaseProcessor):

    def __repr__(self):
        return f'<MaltaGroundwaterProcessor> {self.name}'

    def set_job_id(self, job_id: str):
        self.job_id = job_id

    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)
        self.supports_outputs = True # TODO: Is this not outdated/deprecated by now? Check!
        self.job_id = None
        self.process_id = self.metadata["id"]
        self.image_name = 'maltagw:20251201'

        # Set config:
        config_file_path = os.environ.get('AQUAINFRA_CONFIG_FILE', "./config.json")
        with open(config_file_path, 'r') as config_file:
            config = json.load(config_file)
            self.docker_executable = config["docker_executable"]

            # Where outputs - and inputs that must be downloaded during the
            # process - can be stored and accessed (has to be mounted read-write)
            self.download_dir = config["download_dir"].rstrip('/')
            self.download_url = config["download_url"].rstrip('/')



    def execute(self, data, outputs=None):
        LOGGER.info("Starting to run Malta Groundwater process...")

        ###################
        ### User inputs ###
        ###################

        # Get the inputs:
        user_sealevels = data.get('user_sealevels', None)
        sealevel_int = data.get('sealevel_int', None)
        user_recharge = data.get('user_recharge', None)


        # Check if the numbers are the correct numeric format
        # (unless they are not set)
        if sealevel_int is None:
            pass
        else:
            try:
                sealevel_int = int(sealevel_int)
            except TypeError as e:
                err_msg = 'sealevel_int ("%s") is not an integer, but a "%s"' % (sealevel_int, type(sealevel_int))
                LOGGER.error(err_msg)
                raise ProcessorExecuteError(err_msg)

        if user_recharge is None:
            pass
        else:
            try:
                user_recharge = float(user_recharge)
            except TypeError as e:
                err_msg = 'user_recharge ("%s") is not a float, but a "%s"' % (user_recharge, type(user_recharge))
                LOGGER.error(err_msg)
                raise ProcessorExecuteError(err_msg)

        if user_sealevels is None:
            pass



        #######################
        ### Inputs, outputs ###
        #######################

        # Where to store output data (will be mounted read-write into container):
        output_dir = f'{self.download_dir}/out/{self.process_id}/job_{self.job_id}'
        output_url = f'{self.download_url}/out/{self.process_id}/job_{self.job_id}'
        os.makedirs(output_dir, exist_ok=True)
        LOGGER.debug(f'All results will be stored     in: {output_dir}')
        LOGGER.debug(f'All results will be accessible in: {output_url}')


        ##############################
        ### Run model in container ###
        ##############################

        script_args = []
        if user_sealevels is not None:
            script_args.append("--user_sealevels")
            script_args.append(str(user_sealevels))
        if sealevel_int is not None:
            script_args.append("--sealevel_int")
            script_args.append(str(sealevel_int))
        if user_recharge is not None:
            script_args.append("--user_recharge")
            script_args.append(str(user_recharge))

        LOGGER.debug('SCRIPT ARGS: %s' % script_args)

        '''
        docker run it  maltagw:latest \
          --user_sealevels "[-3.0, -2.0, -1.0]" \
          --sealevel_int 250 \
          --user_recharge 0.002
        '''

        returncode, stdout, stderr, user_err_msg = self.run_docker_container(
            self.docker_executable,
            self.image_name,
            self.job_id,
            output_dir,
            script_args
        )

        if not returncode == 0:
            user_err_msg = "no message" if len(user_err_msg) == 0 else user_err_msg
            err_msg = 'Running docker container failed: %s' % user_err_msg
            raise ProcessorExecuteError(user_msg = err_msg)


        #############################
        ### Prepare response JSON ###
        #############################

        # The output is currently one NetCDF file with the name of: salt_flow.nc
        output_netcdf_file = output_dir+'/salt_flow.nc'
        output_netcdf_url  = output_url+'/salt_flow.nc'


        # Prepare JSON object that will be returned to user:
        # TODO: Anything else, logs, ...?
        response_object = {
            "outputs": {
                "netcdf_output_file": {
                    "title": self.metadata['outputs']['netcdf_output_file']['title'],
                    "description": self.metadata['outputs']['netcdf_output_file']['description'],
                    "href": output_netcdf_url
                }
            }
        }

        # Return link to dir:
        LOGGER.info('This will be the response: %s' % response_object)
        return 'application/json', response_object



    def run_docker_container(
            self,
            docker_executable,
            image_name,
            job_id,
            output_dir,
            script_args
        ):
        LOGGER.debug('Prepare running docker container (image: %s)' % image_name)

        # Create container name # TODO or use process_id?
        # Note: Only [a-zA-Z0-9][a-zA-Z0-9_.-] are allowed
        #container_name = "%s_%s" % (image_name.split(':')[0], os.urandom(5).hex())
        container_name = "%s_%s" % (image_name.split(':')[0], job_id)

        # Replace paths in args, convert args to formats that can be passed to
        # docker and understood/parsed in R script inside docker:
        #LOGGER.debug('Script args: %s' % script_args)

        # Prepare container command
        docker_args = [
            docker_executable, "run", "--rm",
            "--name", container_name
        ]

        # Add the mounts for all the files and directories (-v) (ro and rw):
        # Currently, we only have to mount the directory where the output netcdf will be stored:
        docker_args = docker_args + ["-v", f"{output_dir}:/out:rw"]

        # Add the name of the image
        docker_args = docker_args + [image_name]

        # Add the arguments to be passed to the script:
        if len(script_args) == 0:
            docker_command = docker_args
        else:
            docker_command = docker_args + script_args

        # Run container
        LOGGER.debug('Docker command: %s' % docker_command)
        try:
            LOGGER.debug('Start running docker container (image: %s, name: %s)' % (image_name, container_name))

            result = subprocess.run(docker_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout = result.stdout.decode()
            stderr = result.stderr.decode()
            LOGGER.debug('Finished running docker container (image: %s, name: %s)' % (image_name, container_name))

            # Print docker output:
            log_docker_output(stdout, stderr)

            return result.returncode, stdout, stderr, "no error"

        except subprocess.CalledProcessError as e:
            returncode = e.returncode
            stdout = e.stdout.decode()
            stderr = e.stderr.decode()
            LOGGER.debug('Failed running docker container (exit code %s)(image: %s, name: %s)' % (returncode, image_name, container_name))
            log_docker_output(stdout, stderr)
            user_err_msg = get_error_message_from_docker_stderr(stderr)
            return returncode, stdout, stderr, user_err_msg


