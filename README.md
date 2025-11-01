# DEM Processing and SLC Download

This project provides a pipeline for generating Digital Surface Models (DSMs) using Sentinel-1 data and downloading Single Look Complex (SLC) data. It consists of two main scripts: `slc_dl.py` and `dsm.py`.

## Prerequisites

- **Python Environment**: Ensure you have Python installed and set up with necessary packages.
- **SNAP (Sentinel Application Platform) Toolbox**: You need to have SNAP installed for running DEM processing. Download it from [SNAP Toolbox](https://step.esa.int/updatecenter/9.0/snap-toolboxes/).
- **SNAPHU**: This tool is necessary for unwrapping interferograms. Follow the installation guide [here](https://web.stanford.edu/group/radar/softwareandlinks/sw/snaphu/).
- **STSA**: Install the STSA tool using `pip install git+https://github.com/pbrotoisworo/s1-tops-split-analyzer.git`.

## Installation

1. **SNAPHU Installation**:
   ```bash
   wget https://web.stanford.edu/group/radar/softwareandlinks/sw/snaphu/snaphu-v2.0.7.tar.gz
   mkdir -p ~/snaphu
   cd ~/snaphu
   unzip ~/snaphu-v1.4.2_linux.zip
   cd snaphu-v1.4.2_linux/bin
   chmod +x snaphu
   echo 'export PATH=$PATH:~/snaphu/snaphu-v1.4.2_linux/bin' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **HDF5 Library Issue Fix**:
   If you encounter issues with HDF5 loading during SNAPHU operations, execute:
   ```bash
   export LD_LIBRARY_PATH=$HOME/.snap/auxdata/hdf_natives/12.0.1/amd64:$LD_LIBRARY_PATH
   echo "snap.dataio.hdf.enable=false" >> ~/.snap/etc/snap.properties
   ```

## Usage

### `slc_dl.py` - Downloading SLC Data

- **Objective**: Downloads Sentinel-1 SLC data using ASF's platform.
- **Download Link**: Access the ASF search platform [here](https://search.asf.alaska.edu).
- **Configuration**: Ensure your Earthdata credentials are correctly configured in the environment or `.netrc` file.

### `test_dem2.py` - Generating DSM

- **Objective**: Process Sentinel-1 data to create DSM.
- **Configuration**: Adjust script paths to point to your data directories.
- **References and Tutorials**: Helpful resources for understanding and running the pipeline are available here:
  - [Forum Tutorial](https://forum.step.esa.int/t/how-to-install-snaphu-on-mac-osx-and-windows-for-unwrapping-insar-images/23501)
  - [DEM Generation Tutorial](https://step.esa.int/docs/tutorials/S1TBX%20DEM%20generation%20with%20Sentinel-1%20IW%20Tutorial.pdf)
  - [Earthdata Recipe](https://www.earthdata.nasa.gov/learn/data-recipes/create-dem-using-sentinel-1-data#toc-unwrap-an-interferogram-with-snaphu)

Ensure environmental variables and dependencies are correctly set for a smooth execution of the scripts.
