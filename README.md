# LandsatFire



This code contains an implementation of the Landsat-8 fire detection algorithm by [Schroeder et al. 2016](https://www.sciencedirect.com/science/article/pii/S0034425715301206). This technique uses information from Landsat bands 1–7 to calculate whether an active fire is present at each pixel location. 

<img src="https://github.com/horizonmaps/landsatfire/blob/main/Images/Landsat%20Fire%20752%20Image.jpg">

*Example 752 composite Landsat-8 image showing extracted fire areas*

## Table of contents
  * [Installation and running](#installation-and-running)
  * [Input files](#input-files)
  * [Output](#output)
  * [Warnings](#warnings)
  * [Background](#background)
      - [Input data](#input-data)
      - [Internal calculations](#internal-calculations)
      - [Weighting the calculation](#weighting-the-calculation)
        * [Weighted Means](#weighted-means)
        * [Weighted Standard Deviation](#weighted-standard-deviation)
      - [Edge handling](#edge-handling)
   * [Future updates](#future-updates)

## Installation and running

LandsatFire requires functionality from several other libraries to run, most of which are contained within the Python Standard Library. The four non-standard libraries required are:
- [NumPy](https://numpy.org/install/)
- [SciPy](https://www.scipy.org/install.html)
- [GDAL](https://gdal.org/api/python.html) (gdal, ogr and osr libraries)
- [Rasterio](https://rasterio.readthedocs.io/en/latest/installation.html#)


LandsatFire can be run from the command line or using a GUI. When running the code, keyword arguments can be used; currently there are two kwarg options _writevals_ (set to **False** by default) and _mask_edges_ (set to **True** by default). Running the code with the _writevals_=**True** flag and mask_edges=**False** flag:

```
python landsatfire.py writevals=True mask_edges=False
```

will (a) **not** mask the outermost 30 pixels of the array as background pixels, irrespective of their values (see SECTION below) and (b) write the classified array of pixel values as a GeoTiff file to disk. Irrespective of the writevals setting, a shapefile containing the classified pixel values will be created. All output files are created in the same folder as the input Landsat bands. 

All of the above libraries can be installed using the Anaconda Python distribution. 

**Please note**:  this code was written and tested on macOS; all functionality should work correctly under Windows, however, this has not been tested at present. Please let me know if you encounter any compatibility issues, and I will try to implement the required fixes in a future version of the program. 

## Input files

When running the code, the Landsat-8 files will be read in using the tkinter interface. The program currently expects 32-bit floating point format GeoTiff files as an input. Note that the code has not been tested using 16-bit GeoTiff files, and may  crash or produce an incorrect output if used in this way.

Currently file names require a flag prior to the file extension of the type '_B1' for band 1, for example. This is the standard naming convention for Level-1 Landsat products and also matches the name outputs from my LandsatMenu code. 

**Examples of acceptable file names:**
```
LC08_L1TP_227074_20190825_20190903_01_T1_B5.TIF
LC08_L1TP_227074_20190825_20190903_01_T1_TOA_B5.TIF
my_landsat_file_B5.TIF
```

Note that this type of naming is required for all bands; the code uses these flags to automatically check which bands have been loaded. Future implementations may add options for specifying file locations via a text file and for non-standard file naming.

## Output

LandsatFire, by default, will return an ESRI Shapefile (.shp) with polygons containing different pixel classes. These are listed as a numeric value in the ‘Value' field of the shapefile and as a text string in the ‘Class’ field of the shapefile. The four different pixel classes are as follows:

|Class|Value|Description|
|---|---|---|
|Background|0|Background pixel locations, i.e. those which do not fall into one of the other three classes|
|DN Folding|1|Pixel locations where DN folding is detected, i.e. where channel 7 reflectance values have been identified as anomalously low, due to pixel saturation in areas of highly energetic fire cores.|
|Unambiguous|2|Pixel locations identified as likely containing unambiguous fires.|
|Potential Fire|3|Pixel locations where potential fires have been detected, based on analysis over a 61x61 pixel moving window of background pixels.|

An example image from QGIS showing the different pixel classes is shown below:

<img src = "https://github.com/horizonmaps/landsatfire/blob/main/Images/Landsat%20Pixel%20Classes%20Diagram-01.jpg" width="1000">

## Warnings

The code performs a number of basic 'sanity checks' during file loading to ensure that the input files are, at least superficially, appropriate for use in the later calculation steps. These include checking that all bands are the same size and that no dimension of the image is less than 61 pixels in size. 

The code has been tested on 32-bit single-band floating point GeoTiff files, as described above, up to 7500 x 7500 pixels in size (full Landsat-8 scene size). 

Please be warned that the use of **any other file types**, e.g. non 32-bit images, multi-band images, non-GeoTiff file formats, non-Landsat images, extremely large or extremely small images, etc, is likely to produce incorrect results at best or crash the code/your PC at worst, and choosing to do so is **at your own risk!**

However, if something that **should** work in this code does not appear to work, then please  get in touch and I'll do my best to look into the issue.

## Background

LandsatFire uses a fully vectorised approach to all internal calculations, primarily within NumPy arrays.  

#### Input data 

LandsatFire is designed to work on top-of-atmosphere (TOA) corrected Level-1 Landsat 8 data products. These can be obtained by applying the TOA reflectance algorithm to the raw Level-1 data:

![formula](https://render.githubusercontent.com/render/math?math=\Large\rho_{\lambda}^\prime={M_{\rho}}{Q_{cal}}{A_{\rho}})

Where:

![formula](https://render.githubusercontent.com/render/math?math=\rho_{\lambda}^\prime) is TOA planetary reflectance, without correction for solar angle.

![formula](https://render.githubusercontent.com/render/math?math={M_{\rho}})
is the band-specific multiplicative rescaling factor from the MTL file

![formula](https://render.githubusercontent.com/render/math?math={Q_{cal}}) is the band-specific additive rescaling factor from the metadata

This correction can be achieved using the LandsatMenu program (in development, to be added soon).

#### Internal calculations

Most of the internal calculations within LandsatFire are performed using NumPy logical tests, either by comparing arrays with one another or by comparing array values to some constant. 

The calculation of **potential fire** pixel locations is more complex; the original algorithm by Schroeder et al. (2016) requires calculation of the mean and standard deviation of band 7 and the band 7/5 ratio from valid background pixels over a 61x61 pixel moving window. This calculation can be performed trivially by looping over both axes of each array, but this approach is **extremely** slow and computationally inefficient. 

To perform this calculation, I instead developed a fully vectorised solution, using the uniform filter function from SciPy’s multidimensional image processing library (scipy.ndimage.uniform_filter) on a 61x61 window size. There were two key aspects to this implementation: weighting the calculation, and calculating standard deviations.

```python
b7_means = nd.uniform_filter(mask_band7,size=61)
b7_means /= weights
```

To perform this calculation, I instead developed a fully vectorised solution, using the uniform filter function from SciPy’s multidimensional image processing library ([scipy.ndimage.uniform_filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.uniform_filter.html)) on a 61x61 window size. There were two key aspects to this implementation: weighting the calculation, and calculating standard deviations.

#### Weighting the calculation

Weighting the calculation firstly required a mask array containing the locations of valid background pixels (_bg_mask_); this was generated by the _background_ function. This is a logical array, containing _True_ (1) values where the pixel is a valid background pixel and _False_ (0) values where it is not. I initially ran the uniform_filter on this mask array, which calculated the mean at each pixel location across a 61x61 window. 

```python
weights = nd.uniform_filter(bg_mask,size=61)
```

The mean value represents the fraction of pixels within the window which had a value of **1**; for example, if half the pixels in the 61x61 window were valid background pixels, the calculated mean would be **0.5**. The resulting array of means was used as the weights for subsequent calculation steps (weights array).

Masked versions of band 7 and the band 7/5 ratio were also created separately (_mask_band7, mask_ratio75_) using numpy.ma functionality. Note that these arrays required the inverse of the mask from the background function, i.e., a logical array containing True values where the pixel is **not** a valid background pixel and False values where it is valid. This approach was required because masked arrays in NumPy are generated on the basis of True values relating to array elements which should be masked. 

##### Weighted Means

Calculating weighted means for band 7 and the band 7/5 ratio was fairly straightforward. The uniform filter was applied to the masked version of each band, and the result was divided by the weights array, for example:
```python
b7_means = nd.uniform_filter(mask_band7,size=61)
b7_means /= weights
```

##### Weighted Standard Deviation

Calculating standard deviation for each window is less trivial. Consider the equation for standard deviation:

![formula](https://render.githubusercontent.com/render/math?math=\sigma=\sqrt{mean(x-mean[x])^2})

Superficially, this would require each window's mean value to be subtracted from each element in the 61x61 window. This would potentially require the calculation to be performed on sub-arrays, which risks losing the vectorisation advantage of the code. However, an excellent solution to this problem was proposed by Robert Xiao on [Stack Overflow](https://stackoverflow.com/a/18422519) which uses the linearity of the mean operator to simplify the problem. 

Therefore, let us express mean as an expectation operator, E[x]. Considering only the term inside the square root, we can rewrite the equation as:

![formula](https://render.githubusercontent.com/render/math?math=E[(x-E[x])^2])

Expanding the bracket yields:

![formula](https://render.githubusercontent.com/render/math?math==E[x^2-2xE[x]%2BE[x]^2])

We can multiply through by the E operator term:


![formula](https://render.githubusercontent.com/render/math?math==E[x^2]-E[2xE[x]]%2BE[E[x]^2])

This equation can be simplified because the mean of a mean value is the same as the original value, e.g. ![formula](https://render.githubusercontent.com/render/math?math=E[E[x]=E[x])

Therefore:

![formula](https://render.githubusercontent.com/render/math?math==E[x^2]-2E[x]E[x]%2BE[x]^2)

![formula](https://render.githubusercontent.com/render/math?math==E[x^2]-2E[x]^2%2BE[x]^2)

Finally, by gathering terms:

![formula](https://render.githubusercontent.com/render/math?math==E[x^2]-E[x]^2)

Therefore, the standard deviation can be expressed as: 

![formula](https://render.githubusercontent.com/render/math?math=\sigma=\sqrt{E[x^2]-E[x]^2})

This simplifies the calculation considerably — now, only the ![formula](https://render.githubusercontent.com/render/math?math=E[x^2]) and ![formula](https://render.githubusercontent.com/render/math?math=E[x]) terms are required to calculate the standard deviation.

Using this approach, I calculated the weighted standard deviation as follows:

```python
#Create an array of x^2 values and calculate means on a moving window
b7_squares = nd.uniform_filter(mask_band7*mask_band7,size=61)

#Weighting the x^2 array 
b7_squares /= weights
b7_stddev = ((b7_squares - b7_means*b7_means)**0.5)
```

#### Edge handling

In a non-edge area of the image, the filter kernel will calculate the mean and standard deviation of all valid background pixels (in this example, a 5 x 5 pixel moving window, but in the actual code a 61 x 61 pixel window is used) . The calculation will be then weighted by how many valid pixels were within the filter. In this simple case, let us assume that all pixels with a zero value (i.e. black pixels) are non-valid:

<img src="https://github.com/horizonmaps/landsatfire/blob/main/Images/Landsat%20Fire%20Boundary-02.jpg" width="500">

As shown, 11 pixels are non-valid (numbered); the remaining 14 are valid and are used in the weighted mean/standard deviation calculations.

When the filter kernel is at, or close to, the **edge** of the image, an issue arises that some areas of the kernel would lie **outside** the image. To correct this problem, scipy’s uniform_filter includes a ‘mode’ parameter to specify how these areas should be handled. In LandsatFire, the ‘mode’ parameter is set to ‘constant’ with a value of zero. This means that in edge areas, the filter kernel will fill all areas beyond the edge of the image with pixels containing a **zero value**. In the example below, the 5 x 5 pixel filter is centred on the upper-leftmost pixel in the image, and a 2-pixel wide buffer containing zero values has been added around the edge:

<img src="https://github.com/horizonmaps/landsatfire/blob/main/Images/Landsat%20Fire%20Boundary-03.jpg" width="500">

As the edge pixels all contain zero, they are not treated as valid background pixels and are, thus, not used in the mean/standard deviation calculation and do not contribute to the weighting for this area. 

In the case of LandsatFire, this type of behaviour is particularly important for two reasons. First, in image edge areas it is crucial that the code does not erroneously predict fire pixels due to extrapolating valid data to areas outside the image boundary. Second, when considering full-size Landsat scenes, the Landsat data swaths are not north-south oriented. In UTM coordinate systems, Landsat-8 Level-1 images usually have a black boundary in areas where data was not collected, e.g.

<img src="https://github.com/horizonmaps/landsatfire/blob/main/Images/Landsat%20Fire%20Boundary%20Image.jpg" width="500">

## Future updates
Please note that the code is still in development. There are a number of areas that will be potentially added in future releases, incuding:
* Batch text file reading
* Pure GDAL implementation
* Non-standard file names
* Multi-threading
* Image plotting
