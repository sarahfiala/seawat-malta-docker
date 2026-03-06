FROM ubuntu:24.04

# Set environment variables to avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python3, pip, and dependencies for virtual environment

# Set the working directory in the container
WORKDIR /app


# Install Python3, pip, and dependencies for virtual environment
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
	vim \
	unzip \
	gfortran \
    && apt-get clean


# Create a virtual environment
RUN python3 -m venv /venv

# Use the virtual environment's pip to install dependencies
COPY ./requirements.txt ./
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

# Set the virtual environment as the default for running commands
ENV PATH="/venv/bin:$PATH"

# Install Wine:
RUN dpkg --add-architecture i386
RUN apt update && apt -y install wine wine32:i386 wine64 winbind xvfb

# Copy and unzip
RUN mkdir -p /app/SEAWAT
COPY /SEAWAT /app/SEAWAT
#COPY ./swt_v4x64.exe /app/SEAWAT/swt_v4.exe
RUN chmod ugo+x /app/SEAWAT/swt_v4.exe


#link to the python virtual enviornment
RUN ln -s /venv /app/



#COPY THE FOLDERS RELATED TO SEAWAT RUN
RUN mkdir -p /app/example_inputs
COPY ./example_inputs/ /app/example_inputs
RUN gunzip -f /app/example_inputs/*.gz

RUN mkdir -p /app/model_files

RUN mkdir -p /app/SCRIPTS
COPY ./SCRIPTS/ /app/SCRIPTS

RUN mkdir -p /out



# Add an entrypoint that can deal with CLI arguments that contain spaces:
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

