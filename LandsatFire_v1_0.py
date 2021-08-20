"""
LandsatFire v1.0
Horizon Maps 2021

This code contains an implementation of the Landsat-8 fire detection algorithm 
by Schroeder et al. 2016. This technique uses information from Landsat bands 
1–7 to calculate whether an active fire is present at each pixel location.

For documentation and a sample dataset, please see the GitHub repository at:
https://github.com/horizonmaps/landsatfire
"""

#MODULE IMPORTS

import distutils.util
import os
import os.path
from osgeo import gdal, ogr, osr
import numpy as np
import numpy.ma as ma
from pathlib import Path
import rasterio as rio
import re
import scipy.ndimage as nd
import sys
import time
from tkinter import Tk
import tkinter.filedialog

args = sys.argv

#TKINTER FILE I/O INITIALISATION
root = Tk()
root.withdraw()

#BANDS DICTIONARY
bands_dict = {"1":"Coastal Aerosol","2":"Blue","3":"Green","4":"Red","5":"NIR",
             "6":"SWIR 1","7":"SWIR 2","8":"Panchromatic","9":"Cirrus",
             "10":"TIRS 1","11":"TIRS 2"}

"""
KWARG PROCESSING
"""

def process_args(args):
    """
    Basic kwarg handler to process input list of keyword arguments from the 
    commandline and return a dictionary of values.

    Parameters
    ----------
    args : LIST
        List of kwargs from command line.

    Returns
    -------
    args_dict : DICT
        Dictionary of kwargs, split by '=' sign.

    """
    ks = []
    vs = []
    for arg in args[1:]:
        k,v = arg.split('=')
        ks.append(k)
        vs.append(v)
        
    args_dict = dict(zip(ks,vs))
    
    return args_dict

"""
*****
FILE LOADING FUNCTIONS
*****
"""

def get_filenames():
    """
    This function opens a Tkinter window to get user input. Any number of 
    files can be selected, and the function returns a list containing the file
    paths.

    Returns
    -------
    fnames : LIST
        List object containing file paths.

    """
    fnames = tkinter.filedialog.askopenfilenames()
    root.update()
    return fnames


def get_bands(fnames):
    """
    This function takes a list of file paths and returns lists of the 
    corresponding file names and band numbers.

    Parameters
    ----------
    fnames : LIST
        List object containing file paths.

    Returns
    -------
    band_files : LIST
        List of band file names without associated paths.
    band_numbers : LIST
        List of loaded band numbers.

    """
    band_files = []
    band_numbers = []
    
    for fname in fnames:
        band_files.append(Path(fname).name)
        fnumber = re.search('_B(.+?).',fname)
        if fnumber:
            band_numbers.append(fnumber.group(0).strip('_B').strip('.'))
            
    return band_files, band_numbers


def get_single_band(fnames,band_numbers,band_num):
    """
    Function to return the file path for a single band, given a band number and
    list of input file paths.

    Parameters
    ----------
    fnames : LIST
        List of band file locations, as generated by get_filenames().
    band_numbers : LIST
        List of loaded band numbers.
    band_num : INT
        Numerical value corresponding to a Landsat-8 band.

    Returns
    -------
    STRING
        Returns a string containing the corresponding file path to the input 
        band_num value.

    """
    i = band_numbers.index(str(band_num))
    
    return fnames[i]


def load_fire_bands(band_files,band_numbers):
    """
    Simple function to check Landsat bands 1-8 are loaded for subsequent calculations.

    Parameters
    ----------
    band_files : LIST
        DESCRIPTION.
    band_numbers : LIST
        DESCRIPTION.

    Raises
    ------
    RuntimeError
        DESCRIPTION.

    Returns
    -------
    None.

    """
    file_locs = []
    
    for i in range(1,8):
        if str(i) in band_numbers:
            print("Band "+str(i)+" loaded: "+bands_dict[str(i)])
            b_index = band_numbers.index(str(i))
            print("Band "+str(i)+": "+str(band_files[b_index]))
            temp_loc = get_single_band(band_files,band_numbers,i)
            file_locs.append(temp_loc)
        else:
            raise RuntimeError("Landsat band {bandnum} not loaded".format(bandnum=str(i)))


def check_shapes():
    """
    Sanity check function to ensure that all loaded band arrays have the same
    shape in pixel dimensions. Attempting to run the code with non-equal array
    sizes will at best produce the wrong result and at worst may cause Python
    to crash. This function also checks whether the loaded arrays are <61 pixels
    in size in any dimension.

    Returns
    -------
    shape_test : BOOL
        Returns a boolean value of True if bands 1–7 all have the same
        dimensions and False otherwise.
    size_test : BOOL
        Returns a boolean value of True if either array dimension is <61 pixels
        in size and False otherwise.

    """
    shapes_list = (band1.shape,band2.shape,band3.shape,band4.shape,band5.shape,band6.shape,band7.shape)

    shape_test = shapes_list.count[shapes_list[0]] == len(shapes_list)
    
    size_test = shapes_list[0][0]<61 or shapes_list[0][1]<61
    
    return shape_test,size_test
    
"""
*****
FIRE PIXEL CLASSIFICATION FUNCTIONS
*****
"""

#UNAMBIGUOUS FIRE PIXELS
def unambiguous_fire(write_values=False):
    """
    Internal code to classify unambiguous fire pixels, based on the criteria 
    in Schroeder et al. 2016. 
    
    Uses global arrays for band 5/7 intensity, ratio and difference.
    
    Values can be written to an external array based on the write_values flag.
    
    Parameters
    ----------
    write_values : BOOL, optional
        Specify whether to write the data should be written to an external 
        8-bit GeoTiff file. The default is False.

    Returns
    -------
    criterion_1_fire : BOOL ARRAY
        Returns a NumPy boolean array containing true values where unambiguous 
        fire pixels were detected.

    """
    fire_test_1 = ratio75 > 2.5
    
    fire_test_2 = diff75 > 0.3
    
    fire_test_3 = band7 > 0.5
    
    criterion_1_fire = np.logical_and(fire_test_1,np.logical_and(fire_test_2,fire_test_3))
    
    if write_values == True:
        
        outfire_name = base_name+'_FIRE_PIX.TIF'
        
        dataset=data5
        
        new_dataset = rio.open(outfire_name,mode='w',driver='GTiff',width=criterion_1_fire.shape[1],height=criterion_1_fire.shape[0],count=1,crs=dataset.crs,dtype=np.uint8,transform=dataset.transform)
        new_dataset.write((criterion_1_fire*255).astype(np.uint8),1)
        new_dataset.close()
    
    return criterion_1_fire


#DN FOLDING PIXELS
def dn_fold(write_values=False):
    """
    Internal code to classify DN folding pixels, based on the criteria in
    Schroeder et al. 2016. 
    
    Uses global arrays for band 1 and 5-7 intensity values.
    
    Values can be written to an external array based on the write_values flag.

    Parameters
    ----------
    write_values : BOOL, optional
        Specify whether to write the data should be written to an external 
        8-bit GeoTiff file. The default is False.

    Returns
    -------
    dn_fold_array : BOOL ARRAY
        Returns a NumPy boolean array containing true values where dn folding 
        pixels were detected.

    """
    
    dn_fold_test_1 = band6 > 0.8
    dn_fold_test_2 = band1 < 0.2
    dn_fold_test_3 = band5 > 0.4
    dn_fold_test_4 = band7 < 0.1
    
    dn_fold_criterion_1 = np.logical_and(dn_fold_test_1,dn_fold_test_2)
    dn_fold_criterion_2 = np.logical_or(dn_fold_test_3,dn_fold_test_4)
    
    dn_fold_array = np.logical_and(dn_fold_criterion_1,dn_fold_criterion_2)
    
    if write_values == True:
        
        fold_name = base_name+'_DN_FOLD_PIX.TIF'
        
        dataset=data5
        
        new_dataset = rio.open(fold_name,mode='w',driver='GTiff',width=dn_fold_array.shape[1],height=dn_fold_array.shape[0],count=1,crs=dataset.crs,dtype=np.uint8,transform=dataset.transform)
        new_dataset.write((dn_fold_array*255).astype(np.uint8),1)
        new_dataset.close()
    
    return dn_fold_array


#WATER PIXELS
def water_pixels(write_values=False):
    """
    Internal code to classify water pixels, based on the criteria in  Schroeder 
    et al. 2016. 
    
    This code aims to classify both shallow/sediment-rich water bodies and
    dark/deeper water bodies (tests 7–9 in Schroeder et al.).
    
    Uses global arrays for band 2-7 intensity values and band 1 and 7 difference.
    
    Values can be written to an external array based on the write_values flag.

    Parameters
    ----------
    write_values : BOOL, optional
        Specify whether to write the data should be written to an external 
        8-bit GeoTiff file. The default is False.

    Returns
    -------
    water_pixel_array : BOOL ARRAY
        Returns a NumPy boolean array containing true values where water 
        pixels were detected.

    """
    
    water_criterion_1 = np.logical_and(band4>band5,band5>band6)
    water_criterion_2 = np.logical_and(band6>band7,diff17<0.2)
    
    water_base_criterion = np.logical_and(water_criterion_1,water_criterion_2)
    
    water_criterion_3 = band3 > band2
    water_criterion_4 = np.logical_and(np.logical_and(band1>band2,band2>band3),band3>band4)
    
    water_type_criterion = np.logical_or(water_criterion_3,water_criterion_4)
    
    water_pixel_array = np.logical_and(water_base_criterion,water_type_criterion)
    
    if write_values == True:
        
        water_name = base_name+'_WATER_PIX.TIF'
        
        dataset=data5
        
        new_dataset = rio.open(water_name,mode='w',driver='GTiff',width=water_pixel_array.shape[1],height=water_pixel_array.shape[0],count=1,crs=dataset.crs,dtype=np.uint8,transform=dataset.transform)
        new_dataset.write((water_pixel_array*255).astype(np.uint8),1)
        new_dataset.close()

    return water_pixel_array


#BACKGROUND PIXELS
def background(unambiguous_array,water_array):
    """
    Internal code to classify valid background pixels, i.e. pixels which are
    not flagged as water or unambiguous fire pixels, and have band 7 radiance
    greater than zero.

    Parameters
    ----------
    unambiguous_array : BOOL ARRAY
        Array containing true values where unambiguous fire pixels have been
        indentified, as generated by the unambiguous_fire function.
    water_array : BOOL ARRAY
        Array containing true values where water pixels have been identified,
        as generated by the unambiguous_fire function.

    Returns
    -------
    background_pix : BOOL ARRAY
        Array containing true values where the pixel is a valid background
        pixel, i.e. where the pixel does not contain water or an unambiguous 
        wildfire, and channel 7 reflectance is greater than zero.

    """
    
    background_pix = np.invert(np.logical_or(unambiguous_array,water_array))
    background_pix = np.logical_and(background_pix,band7>0)
    
    
    return background_pix


#POTENTIAL FIRE PIXELS
def potential_fire(bg_array,write_values=False,mask_edges=True):
    """
    Internal code to classify potential fire pixels, using an array of valid 
    background pixels (bg_array). This code performs tests 3-6 from Schroeder
    et al. 2016, using a SciPy uniform filtering approach on a 61x61 element
    moving window. 
    
    Depending on the status of the mask_edges parameter, the outermost 30 pixels 
    of the array can be automatically classified as not potential fire pixels, 
    even if they meet the other criteria. This options is set to True by default
    because the moving window calculation is not performed over a full 61x61
    domain at these pixel locations; however, this may be required in some 
    circumstances, therefore, the option to override this setting is available.
    
    For theoretical considerations of the edge-effect calculations in this code
    and the mathematical approach used, please see the GitHub documentation.
    

    Parameters
    ----------
    bg_array : BOOL ARRAY
        Array containing True values where the pixel is NOT a  valid background
        pixel, as generated by background function.
    write_values : BOOL, optional
        Specify whether to write the data should be written to an external 
        8-bit GeoTiff file. The default is False.
    mask_edges : BOOL, optional
        Specify whether the outer 30 pixels of the image on each axis should be 
        masked, i.e. classified as not potential fire pixels irrespective of 
        whether they meet the other criteria or not.

    Returns
    -------
    potential_array : BOOL ARRAY
        Array containing True values where valid background pixels have been
        classified as potential fire pixels.

    """
    
    #Making an inverted copy of bg_array for masking
    
    bg_inv = np.invert(bg_array)
    
    #Masking local copies of each array
    
    ma_ratio75 = ma.masked_array(ratio75,bg_inv)
    ma_ratio76 = ma.masked_array(ratio76,bg_inv)
    ma_diff75 = ma.masked_array(diff75,bg_inv)
    ma_band7 = ma.masked_array(band7,bg_inv)
    
    potential_test_1 = np.logical_and(ma_ratio75>1.8,ma_diff75>0.17)
    potential_test_2 = ma_ratio76 > 1.6
    
    potential_test_3 = np.logical_and(potential_test_1,potential_test_2)
    
    #Create a 32-bit mask for vectorised filtering
    
    bg_mask = bg_array.astype(np.float32)
    weights = nd.uniform_filter(bg_mask,size=61)
    
    #Masking arrays
    
    mask_band7 = band7 * bg_mask
    mask_ratio75 = ratio75 * bg_mask
    
    #Calculating means
    
    with np.errstate(divide='ignore',invalid='ignore'):
        b7_means = nd.uniform_filter(mask_band7,size=61)
        b7_means /= weights
        
        ratio75_means = nd.uniform_filter(mask_ratio75,size=61)
        ratio75_means /= weights
        
        #Calculating standard deviations
        
        b7_squares = nd.uniform_filter(mask_band7*mask_band7,size=61)
        ratio75_squares = nd.uniform_filter(mask_ratio75*mask_ratio75,size=61)
        
        b7_squares /= weights
        ratio75_squares /= weights
        
        b7_stddev = ((b7_squares - b7_means*b7_means)**0.5)
        ratio75_stddev = ((ratio75_squares - ratio75_means*ratio75_means)**0.5)
        
        b7_stddev*=3
        b7_stddev[b7_stddev<0.08] = 0.08
        
        ratio75_stddev*=3
        ratio75_stddev[ratio75_stddev<0.8] = 0.8
        
        potential_test_4 = np.logical_and(ma_ratio75>ratio75_stddev,ma_band7>b7_stddev)
        
        potential_array = np.logical_and(potential_test_3,potential_test_4)
    
    #Masking edges 
    if mask_edges == True:
        
        potential_array[:30,:] = 0
        potential_array[-30:,:] = 0
        potential_array[:,:30] = 0
        potential_array[:,-30:] = 0
    
    #Writing values to file
    if write_values == True:
        
        potential_name = base_name+'_POTENTIAL_FIRE_PIX.TIF'
        
        dataset=data5
    
        new_dataset = rio.open(potential_name,mode='w',driver='GTiff',width=potential_array.shape[1],height=potential_array.shape[0],count=1,crs=dataset.crs,dtype=np.uint8,transform=dataset.transform)
        new_dataset.write((potential_array*255).astype(np.uint8),1)
        new_dataset.close()
        
    return potential_array


def make_classified_array(dn_fold_array,unambiguous_array,potential_array,write_values=False):
    """
    Code to take arrays of pixel locations containing different classes and 
    generate an output classified array, with numerical values corresponding
    to classification type.

    Parameters
    ----------
    dn_fold_array : BOOL ARRAY
        Array containing True values where dn folding pixels have been identified,
        as generated by the dn_fold function.
    unambiguous_array : BOOL ARRAY
        Array containing true values where unambiguous fire pixels have been
        indentified, as generated by the unambiguous_fire function.
    potential_array : BOOL ARRAY
        Array containing True values where valid background pixels have been
        classified as potential fire pixels.
    write_values : TYPE, optional
        DESCRIPTION. The default is False.

    Returns
    -------
    ARRAY
        An 8-bit array, containing classified pixel values; value 0 corresponds 
        to non-fire pixels, 1 corresponds to DN fold pixels, 2 corresponds to
        unambiguous fire pixels and 3 corresponds to potential fire pixels.

    """
    
    class_arr = np.zeros(dn_fold_array.shape).astype(np.uint8)
    
    class_arr = class_arr + dn_fold_array.astype(np.uint8)
    class_arr = class_arr + (unambiguous_array.astype(np.uint8)*2)
    class_arr = class_arr + (potential_array.astype(np.uint8)*3)
    
    if write_values == True:
        
        water_name = base_name+'_CLASS_PIX.TIF'
        
        dataset=data5
        
        new_dataset = rio.open(water_name,mode='w',driver='GTiff',width=class_arr.shape[1],height=class_arr.shape[0],count=1,crs=dataset.crs,dtype=np.uint8,transform=dataset.transform)
        new_dataset.write(class_arr,1)
        new_dataset.close()
    
    #Note the use of the .data call due to class_arr being a masked array
    return class_arr.data



"""
*****
PRE-FLIGHT
*****

Code to initialise calculation process.

Calls process_args to generate global kwarg dictionary.
Calls get_filenames to get file paths for Landsat bands.
Starts performance counter to measure program execution time.
Makes file name and numbers lists using get_bands.
Calls load_fire_bands as sanity check to ensure all required bands are loaded.
Uses check_shapes as a final sanity check after loading data to ensure that all 
bands have the same dimensions.
"""

#PROCESSING KWARGS
args_dict = process_args(args)

if 'writevals' in args_dict:
    vals_check=bool(distutils.util.strtobool(args_dict['writevals']))
else:
    vals_check=False
    
if 'mask_edges' in args_dict:
    edges_check=bool(distutils.util.strtobool(args_dict['mask_edges']))
else:
    edges_check=True
    
fnames = get_filenames()

t_start = time.perf_counter()
bfiles,bnumbers = get_bands(fnames)

load_fire_bands(bfiles,bnumbers)

print("All required bands loaded.")

#DATA INITIALISATION

#Loading Landsat bands using rio

data1 = rio.open(get_single_band(fnames,bnumbers,1))
data2 = rio.open(get_single_band(fnames,bnumbers,2))
data3 = rio.open(get_single_band(fnames,bnumbers,3))
data4 = rio.open(get_single_band(fnames,bnumbers,4))
data5 = rio.open(get_single_band(fnames,bnumbers,5))
data6 = rio.open(get_single_band(fnames,bnumbers,6))
data7 = rio.open(get_single_band(fnames,bnumbers,7))

band1 = data1.read(1)
band2 = data2.read(1)
band3 = data3.read(1)
band4 = data4.read(1)
band5 = data5.read(1)
band6 = data6.read(1)
band7 = data7.read(1)

#Array shape and size sanity checks on loaded bands

band_shape_check,band_size_check = check_shapes()

if band_shape_check == False:
    raise ValueError("One or more loaded bands do not have equal dimensions. Please check the files you are trying to load.")

if band_size_check == True:
    print("Warning: One or more array dimensions is smaller than 61 pixels. The output is likely to be incorrect. ")

#Creating ratio and difference arrays

ratio75 = band7/band5
ratio76 = band7/band6

diff17 = band1 - band7   
diff75 = band7-band5

base_name = os.path.commonprefix(fnames).strip('_B')


"""
*****
MAIN FUNCTION CALLS
*****
"""

#Calculating unambiguous, DN folding and water pixel classes

unambiguous_pix = unambiguous_fire()
dn_fold_pix = dn_fold()
water_pix = water_pixels()

#Calculating background pixels using unambiguous and water classes

background_pix = background(unambiguous_pix,water_pix)

#Calculating potential fire pixels from valid background pixels

potential_pix = potential_fire(background_pix,mask_edges=edges_check)

#Generating a classified array of pixel values

class_pix = make_classified_array(dn_fold_pix,unambiguous_pix,potential_pix,write_values=vals_check)


""""
*****
SHAPEFILE EXPORT BLOCK
*****

Code to create an ESRI shapefile containing pixel classifications, using GDAL.

A temporary raster file containing the classified pixel array (i.e. the output
from make_classified_array) is written to disk and deleted at the end of code 
execution. This operation is independent of whether the write_values flag is
set to True. 

Once the polygons have been created, the features are looped over and a new
'Class' field is populated, containing the strings 'BACKGROUND', 'DN FOLD',
'FIRE' or 'POTENTIAL FIRE' based on the 'Value' field.

After the GDAL Polygonize operation is complete, a garbage collection is
performed to close the datasets used by GDAL and deallocate the memory. This
operation is necessary to ensure files are correctly written to disk and the
code does not crash, especially when run using a Python GUI.
"""

#Loading reference raster
sourceRaster = gdal.Open(fnames[0])

#Initialising temporary raster properties
temp_classes = base_name +'_CLASS_TEMP.TIF'

temp_driver = gdal.GetDriverByName('GTiff')

x_pix = class_pix.shape[1]
y_pix = class_pix.shape[0]

temp_ds = temp_driver.Create(temp_classes,x_pix,y_pix,1,gdal.GDT_Byte)

temp_ds.SetGeoTransform(sourceRaster.GetGeoTransform())
temp_ds.SetProjection(sourceRaster.GetProjection())

temp_band = temp_ds.GetRasterBand(1)

#Writing temporary raster to disk
temp_band.WriteArray(class_pix)
temp_band.FlushCache()

#Explicitly deallocating dataset
temp_ds = None

#Loading temp dataset back in
in_classes = gdal.Open(temp_classes)
in_band = in_classes.GetRasterBand(1)


#Creating destination shapefile
src_srs = osr.SpatialReference(wkt=sourceRaster.GetProjection())

outShapefile = os.path.join(str(Path(fnames[0]).parent),'Classified_Pixels.shp')

driver = ogr.GetDriverByName("ESRI Shapefile")

dst_ds = driver.CreateDataSource(outShapefile)


#Creating shapefile attributes
outLayer = dst_ds.CreateLayer("polygonized", srs=src_srs)
valField = ogr.FieldDefn('Value', ogr.OFTInteger)
clField = ogr.FieldDefn("Class",ogr.OFTString)
outLayer.CreateField(valField)
outLayer.CreateField(clField)


#Polygonizing raster band
gdal.Polygonize(in_band, None, outLayer, 0, [], callback=None)


#Iterating over shapefile features and populating Class field
outLayer.ResetReading()

out_classes = ['BACKGROUND','DN FOLD','FIRE','POTENTIAL FIRE']
feature = outLayer.GetNextFeature()

while feature:
    i = feature.GetField('Value')
    feature.SetField("Class",out_classes[i])
    outLayer.SetFeature(feature)
    feature = outLayer.GetNextFeature()


#Garbage collection 
os.remove(temp_classes)
in_band = None

del sourceRaster

dst_ds = None
outLayer = None

#PERFORMANCE STATISTICS
t_end = time.perf_counter()
print(f"File processing completed. Time taken: {t_end-t_start:0.2f} seconds")