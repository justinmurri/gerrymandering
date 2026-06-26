# much of this code is attributed to Porter--Feng (as it is a straightforward modification of their levelset algorithm), their code available at https://github.com/mhcfeng/precinct

# import GDAL
from osgeo import ogr, osr, gdal 
import numpy as np
import matplotlib.pyplot as plt
import time
import logging
import gudhi
import pandas
import csv
print(dir(gdal))

import csv
from matplotlib import collections  as mc
import matplotlib.pyplot as pl
from pylab import MaxNLocator
import numpy as np
import os.path
import logging


BLUE_VOTES = "G20PREDBID" #adjust as needed
RED_VOTES = "G20PRERTRU" #adjust as needed
RED_MARGIN = "RED_MAR"
BLUE_MARGIN = "BLUE_MAR"
IS_RED = "IS_RED"
IS_BLUE = "IS_BLUE"
DENSITY = "MAR"
NO_DATA_VALUE = -99999
REPUBLICAN = 0
DEMOCRAT = 1
BOTH = 2


TABLE_NAME = "ut_vest_20" #adjust as needed
AREA = "district"
year = "2020" #adjust as needed
state = "ut"
root = '/Users/justinmurri/Gerrymander-Research/topology_analysis/' #adjust as needed
STATE_RASTER = root + 'ut_rasters_' + year + '/ut.tif'
STATE_TIF_R  = root + 'ut_tif_r_' + year + '.tif'
STATE_TIF_D  = root + 'ut_rasters_' + year + '/ut_tif_d.tif'
STATE_MARGIN = root + 'ut_rasters_' + year + '/ut_tif_margins.tif'
STATE_BARCODE = root + 'ut_barcode_' + year + '.csv'
LEVEL_SET    = root + 'ut_rasters_' + year + '/levelset_step_'
STATE_VERTICES = root + 'ut_vertices_' + year + '.csv'
SHP = '/Users/justinmurri/Gerrymander-Research/topology_analysis/ut_vest_20/ut_vest_20.shp' #adjust as needed


def compute_margins(shp):
    data = gdal.OpenEx(shp, gdal.OF_VECTOR | gdal.OF_UPDATE)
    print(type(data))
    data.ExecuteSQL("ALTER TABLE " + TABLE_NAME + " DROP COLUMN " + RED_MARGIN)
    data.ExecuteSQL("ALTER TABLE " + TABLE_NAME + " DROP COLUMN " + BLUE_MARGIN)
    data.ExecuteSQL("ALTER TABLE " + TABLE_NAME + " DROP COLUMN " + IS_BLUE)
    data.ExecuteSQL("ALTER TABLE " + TABLE_NAME + " DROP COLUMN " + IS_RED)
    data.ExecuteSQL("ALTER TABLE " + TABLE_NAME + " DROP COLUMN " + DENSITY)
    data = None

    source = ogr.Open(shp, 1)
    tx_layer = source.GetLayer(0)    
    tx_2016 = source.GetLayer(0).GetLayerDefn()
    num_fields = tx_2016.GetFieldCount()

    red_margin = ogr.FieldDefn(RED_MARGIN, ogr.OFTInteger)
    blue_margin = ogr.FieldDefn(BLUE_MARGIN, ogr.OFTInteger)
    is_red = ogr.FieldDefn(IS_RED, ogr.OFTInteger)
    is_blue = ogr.FieldDefn(IS_BLUE, ogr.OFTInteger)
    tx_layer.CreateField(red_margin)
    tx_layer.CreateField(blue_margin)
    tx_layer.CreateField(is_red)
    tx_layer.CreateField(is_blue)

    #white color for non-colored utah precincts
    red = ogr.FieldDefn("COLOR_R", ogr.OFTInteger)
    green = ogr.FieldDefn("COLOR_G", ogr.OFTInteger)
    blue = ogr.FieldDefn("COLOR_B", ogr.OFTInteger)
    margin_density = ogr.FieldDefn(DENSITY, ogr.OFTReal)
    tx_layer.CreateField(red)
    tx_layer.CreateField(green)
    tx_layer.CreateField(blue)
    tx_layer.CreateField(margin_density)
    #Each feature is a polygon. Each one has values for all the fields, which are named tx_2016.GetFieldDefn(i).GetName()
    for precinct in tx_layer:
        precinct_red_votes = float(precinct.GetField(RED_VOTES))
        precinct_blue_votes = float(precinct.GetField(BLUE_VOTES))
        precinct.SetField(RED_MARGIN, precinct_red_votes - precinct_blue_votes)
        precinct.SetField(BLUE_MARGIN, precinct_blue_votes - precinct_red_votes)
        #precinct.GetGeometryRef().Transform(trans)
        area = max(1, precinct.GetGeometryRef().GetArea()/5000000.0)
        #area = max(1, precinct.GetGeometryRef().GetArea()/1.0)
        #area = max(1, precinct.GetField(AREA)/1000000.0)
        print(area)
        print(precinct.GetGeometryRef().GetArea())
        d = abs(precinct_red_votes - precinct_blue_votes)/float(area)
        d = max(1, d)
        d = min(255, d)
        d = 256 - d
        precinct.SetField(DENSITY, d)
        #IS_RED is 255 (white) if blue and 0 (colored) if red
        precinct.SetField(IS_RED, (int(precinct_red_votes < precinct_blue_votes))*255)
        precinct.SetField(IS_BLUE, (int(precinct_blue_votes <  precinct_red_votes))*255)
        tx_layer.SetFeature(precinct)
    source = None

def rasterize_shp(shp, out_tiff, party, max_pixels, margin_tiff):
    source_ds = gdal.OpenEx(shp, gdal.OF_VECTOR | gdal.OF_UPDATE)

    source_ds = None

    source_ds = ogr.Open(shp, 1)
    source_layer = source_ds.GetLayer(0)
    x_min, x_max, y_min, y_max = source_layer.GetExtent()
    max_cols = max_rows = max_pixels
    max_pixel_width = (x_max - x_min) / max_cols
    max_pixel_height = (y_max - y_min) / max_rows
    pixel_width = pixel_height = max(max_pixel_width, max_pixel_height)
    cols = int((x_max - x_min) / pixel_height)
    rows = int((y_max - y_min) / pixel_width)

    target_ds = gdal.GetDriverByName('Gtiff').Create(out_tiff, cols, rows, 1, gdal.GDT_Byte)
    margin_ds = gdal.GetDriverByName('Gtiff').Create(margin_tiff, cols, rows, 1, gdal.GDT_Byte)
    target_ds.SetGeoTransform((x_min, pixel_width, 0, y_max, 0, -pixel_height))
    margin_ds.SetGeoTransform((x_min, pixel_width, 0, y_max, 0, -pixel_height))
    band = target_ds.GetRasterBand(1)
    mband = margin_ds.GetRasterBand(1)
    no_data_value = 0
    band.SetNoDataValue(no_data_value)
    mband.SetNoDataValue(255)
    band.FlushCache()
    mband.FlushCache()
    c = ""
    if party == REPUBLICAN:
        c = IS_RED
    if party == DEMOCRAT:
        c = IS_BLUE
        
    gdal.RasterizeLayer(target_ds, [1], source_layer, options=["ATTRIBUTE=" + c])
    gdal.RasterizeLayer(margin_ds, [1], source_layer, options=["ATTRIBUTE=" + DENSITY])
    target_ds_srs = osr.SpatialReference()
    target_ds_srs.ImportFromEPSG(26912)
    target_ds.SetProjection(target_ds_srs.ExportToWkt())
    source_ds = None
    margin_ds.SetProjection(target_ds_srs.ExportToWkt())
    margin_ds = None

def rasterize(shp, party, pixels, out_tiff):
    source = ogr.Open(shp, 1)
    tx_layer = source.GetLayer()
    tx_2016 = tx_layer.GetLayerDefn()

    x_min, x_max, y_min, y_max = tx_layer.GetExtent()
    pixel_size = max((x_max - x_min)/pixels, (y_max - y_min)/pixels)
    cols = int((x_max - x_min)/pixel_size)
    rows = int((y_max - y_min)/pixel_size)

    outfile = gdal.GetDriverByName("Gtiff").Create(out_tiff, cols, rows, 3, gdal.GDT_Byte)
    outfile.SetGeoTransform((x_min, pixel_size, 0, y_max, 0, -pixel_size))
    band = outfile.GetRasterBand(1)
    band.SetNoDataValue(NO_DATA_VALUE)
    band.FlushCache()

    if party == REPUBLICAN:
        for precinct in tx_layer:
            if precinct.GetField(RED_MARGIN) > 0:
                precinct.SetField("COLOR_R", 255)
                precinct.SetField("COLOR_B", 0)
                precinct.SetField("COLOR_G", 0)
            else:
                precinct.SetField("COLOR_R", 127)
                precinct.SetField("COLOR_B", 127)
                precinct.SetField("COLOR_G", 127)
            tx_layer.SetFeature(precinct)
        gdal.RasterizeLayer(outfile, [1], tx_layer, options = ["ATTRIBUTE=COLOR_R"])
        gdal.RasterizeLayer(outfile, [2], tx_layer, options = ["ATTRIBUTE=COLOR_G"])
        gdal.RasterizeLayer(outfile, [3], tx_layer, options = ["ATTRIBUTE=COLOR_B"])


    elif party == DEMOCRAT:
        for precinct in tx_layer:
            if precinct.GetField(BLUE_MARGIN) > 0:
                precinct.SetField("COLOR_R", 0)
                precinct.SetField("COLOR_G", 0)
                precinct.SetField("COLOR_B", 255)
            else:
                precinct.SetField("COLOR_R", 127)
                precinct.SetField("COLOR_G", 127)
                precinct.SetField("COLOR_B", 127)
            tx_layer.SetFeature(precinct)
        gdal.RasterizeLayer(outfile, [1], tx_layer, options = ["ATTRIBUTE=COLOR_R"])
        gdal.RasterizeLayer(outfile, [2], tx_layer, options = ["ATTRIBUTE=COLOR_G"])
        gdal.RasterizeLayer(outfile, [3], tx_layer, options = ["ATTRIBUTE=COLOR_B"])
    elif party == BOTH:
        for precinct in tx_layer:
            if precinct.GetField(IS_BLUE) == 0:
                precinct.SetField("COLOR_R", 0)
                precinct.SetField("COLOR_G", 0)
                precinct.SetField("COLOR_B", 255)
            else:
                precinct.SetField("COLOR_R", 255)
                precinct.SetField("COLOR_G", 0)
                precinct.SetField("COLOR_B", 0)
            tx_layer.SetFeature(precinct)
        gdal.RasterizeLayer(outfile, [1], tx_layer, options = ["ATTRIBUTE=COLOR_R"])
        gdal.RasterizeLayer(outfile, [2], tx_layer, options = ["ATTRIBUTE=COLOR_G"])
        gdal.RasterizeLayer(outfile, [3], tx_layer, options = ["ATTRIBUTE=COLOR_B"])
            
    outfile_srs = osr.SpatialReference()
    outfile_srs.ImportFromEPSG(4326)
    outfile.SetProjection(outfile_srs.ExportToWkt())
    source = None
    outfile = None

# phi is the function which we want to take the levelset of.
# a specifies the sign 
# Returns the magnitude of the gradient of phi at each point.

def gradient(phi, a):
    phi_p_x = np.zeros(phi.shape)
    phi_n_x = np.zeros(phi.shape)
    phi_p_y = np.zeros(phi.shape)
    phi_n_y = np.zeros(phi.shape)

    phi_p_x[:, 0:-1] = phi[:, 1:] - phi[:, 0:-1]
    phi_n_x[:, 1:] = phi[:, 1:] - phi[:, 0:-1]
    phi_p_y[0:-1, :] = phi[1:, :] - phi[0:-1, :]
    phi_n_y[1:, :] = phi[1:, :] - phi[0:-1, :]

    phi_x_neg = np.maximum(np.power(np.maximum(phi_n_x, 0), 2), np.power(np.minimum(phi_p_x, 0), 2))
    phi_y_neg = np.maximum(np.power(np.maximum(phi_n_y, 0), 2), np.power(np.minimum(phi_p_y, 0), 2))

    phi_x_pos = np.maximum(np.power(np.minimum(phi_n_x, 0), 2), np.power(np.maximum(phi_p_x, 0), 2))
    phi_y_pos = np.maximum(np.power(np.minimum(phi_n_y, 0), 2), np.power(np.maximum(phi_p_y, 0), 2))

    phi_x = -np.minimum(np.sign(a), 0) * phi_x_neg + np.maximum(np.sign(a), 0) * phi_x_pos
    phi_y = -np.minimum(np.sign(a), 0) * phi_y_neg + np.maximum(np.sign(a), 0) * phi_y_pos
    return np.sqrt(phi_x + phi_y)


def sign(phi):
    denom = np.sqrt(np.power(phi, 2) + gradient(phi, np.ones(phi.shape)))
    return np.divide(phi, denom)


def normalize_distance(image, time):
    length, width = image.shape
    c = np.sqrt(length ^ 2 + width ^ 2)
    distances = image.copy()
    distances = distances.astype(float)
    distances = ((distances / 255) * 2 - 1) * c
    sign_phi = sign(distances)
    dt = 1 / (4 * np.max(np.abs(sign_phi)))

    for i in np.arange(time / dt):
        dphi = dt * sign_phi * (1 - gradient(distances, -sign_phi))
        distances = distances + dphi

    return distances


def advance_level_set(image, time, margins):
    a = np.ones(image.shape)
    margins = 256 - margins.astype(np.int32)
    margins = 20 * (1/margins)
    dt = .25

    for i in np.arange(time / dt):
        dphi = -dt * a * gradient(image, a) * margins
        image = image + dphi

    return image

#Given current values of phi and previously added zeros of phi, add new zeros and their entry times.
#N.B. All vertices are given by their position in the flat image array
def write_img_idx_map(image, existing_verts, entry_times, T, end = False):
    #indices (in flattened image) for which phi = 0. We wish to add these.
    curr_verts = np.flatnonzero(image==0)
    if end:
        curr_verts = [i for i in range(image.shape[0] * image.shape[1])]
    r,c = image.shape
    #only consider multiples of 5
    curr_verts = [vert for vert in curr_verts if ((vert%c)%5==0 and (int(vert/c))%5==0)]
    new_verts = list(set(curr_verts).difference(set(existing_verts.keys())))
    n = len(existing_verts)
    #add in new vertices including the information of what order they come in.
    #NB: the new vertices all have the same entry time
    for vert in new_verts:
        existing_verts[vert] = T
        #n += 1
        entry_times.append(T)
    return existing_verts, entry_times

#Now existing_verts is of the form index -> order in time added. entry_times groups together vertices added in the same levelset
# Goes through existing vertices and adds in their adjacencies based on the original flattening of the image array
def gen_img_adjacencies(existing_verts, h, w):
    
    existing_verts_list = list(existing_verts.keys()) #recall the keys are positions in flat image
    adjacencies = {} # associates a vertex to its adjacency list
    for vert in existing_verts_list:
        poss_adj = []
        if vert % w >= 5 and vert % w < w-5:
            poss_adj = [vert-5*w-5, vert-5*w, vert-5, vert+5, vert+5*w, vert+5*w+5, vert + 5*w - 5, vert - 5*w + 5]
        elif vert % w < 5:
            poss_adj = [vert - 5*w, vert - 5*w + 5, vert + 5, vert + 5*w + 5, vert + 5*w]
        elif vert % w >= w-5:
            poss_adj = [vert - 5*w, vert - 5*w - 5, vert - 5, vert + 5*w - 5, vert + 5*w]
        poss_adj = [i for i in poss_adj if i>=0 and i < w*h]
        #poss_adj = list(set(poss_adj).intersection(set(existing_verts_list)))
        adjacencies.update({vert : [neighbor for neighbor in poss_adj]})
    return adjacencies
# each element of adjacencies is a list of vertices which the ith vertex is adjacent to. Vertices are numbered according to their position in flat image


def build_levelset_complex(party, save_plots = True):
    tif_file = ""
    if party == REPUBLICAN:
        tif_file = STATE_TIF_R
    else:
        tif_file = STATE_TIF_D
    margin_file = STATE_MARGIN
    img_array = plt.imread(tif_file)
    margins = plt.imread(margin_file)
    dT = .125
    n = 25
    T = 0
    existing_verts = {}
    entry_times = []
    existing_verts, entry_times = write_img_idx_map(img_array, existing_verts, entry_times, T)
    gamma = 3
    img_array = normalize_distance(img_array, gamma)
    for i in range(n):
        T = T + dT
        img_array = advance_level_set(img_array, dT, margins)
        phi_array_img = (np.sign(img_array) + 1) / 2 * 255

        if save_plots:
            T_out = LEVEL_SET + str(int(T/dT + 0.01)) + '.tiff'
            phi_array_img = phi_array_img.astype(int)
            plt.imsave(T_out, phi_array_img)
            img_array = normalize_distance(phi_array_img, gamma)
        end = False
        if(i == n-1):
            end = True
        existing_verts, entry_times = write_img_idx_map(phi_array_img, existing_verts, entry_times, i, end)
    phi_array_img = np.zeros(img_array.shape)
    phi_array_img = phi_array_img.astype(int)
    #existing_verts, entry_times = write_img_idx_map(phi_array_img, existing_verts, entry_times, n)

    key_write_filename = STATE_VERTICES
    with open(key_write_filename, 'w') as key_file:
        key_writer = csv.writer(key_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for k, v in existing_verts.items():
            key_writer.writerow([str(k), str(v)])
    key_file.close()

    h, w = img_array.shape
    adjacencies = gen_img_adjacencies(existing_verts, h, w)
    #print(adjacencies)


    #NB: we only add simplicial complexes of dimension up to 2
    # Build a gudhi SimplexTree with filtration values equal to the time step
    # each simplex first appears -- equivalent to the original phat boundary matrix.
    st = gudhi.SimplexTree()
    added_verts = set()
    for time in range(n):
        for vert, t in existing_verts.items():
            if t == time:
                st.insert([vert], filtration=time)
                added_verts.add(vert)
                for neighbor in adjacencies[vert]:
                    if neighbor in added_verts:
                        st.insert([neighbor, vert], filtration=time)
                for n1 in adjacencies[vert]:
                    for n2 in adjacencies[vert]:
                        if n1 in added_verts and n2 in added_verts:
                            if n1 in adjacencies[n2]:
                                st.insert([n1, n2, vert], filtration=time)

    print("filtered complex computed. Computing persistent homology...")
    st.compute_persistence()
    persistence = st.persistence()
    print(persistence)

    # Collect H1 pairs (dimension 1) with finite death values
    final_pairs = []
    for dim, (birth, death) in persistence:
        if dim == 1 and death != float('inf'):
            final_pairs.append((1, birth, death))
    print(final_pairs)
    print(str(len(final_pairs)))
    
    csv_file = STATE_BARCODE
    with open(csv_file, 'w') as f:
        writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for pair in final_pairs:
            if pair[0] == 1:
                writer.writerow([str(pair[1]), str(pair[2])])
    f.close()

## MAIN SCRIPT
shp = SHP
compute_margins(shp)
pixels = 1000
rasterize(shp, BOTH, pixels, STATE_RASTER)
rasterize_shp(shp, STATE_TIF_R, REPUBLICAN, pixels, STATE_MARGIN)
build_levelset_complex(REPUBLICAN)


## GENERATING PERSISTENCE BARCODE
#Created on Wed Oct  4 12:31:03 2017

#@author michellefeng

filename  = STATE_BARCODE
savepath = root + state + '_barcode.png'
def parse_csv_to_birth_death(filename):
    with open(filename) as csvfile:
        readCSV = csv.reader(csvfile, delimiter=',')
        data = list(readCSV)
        dim_zero_it=1
        dim_one_it=1
        dim_zero=[]
        dim_one=[]
        for row in data:
            if row[0] == "0":
                #birth_tup = (row[1],dim_zero_it)
                #death_tup = (row[2],dim_zero_it)
                birth_tup = (row[0],dim_zero_it)  # chg 1 to 0
                death_tup = (row[1],dim_zero_it)  # chg 2 to 1
                
                dim_zero.append([birth_tup,death_tup])
                dim_zero_it += 1
            #if row[0] == "1":
            else:
                #birth_tup = (row[1],dim_one_it)
                #death_tup = (row[2],dim_one_it)                
                birth_tup = (row[0],dim_one_it)  # chg 1 to 0
                death_tup = (row[1],dim_one_it)  # chg 2 to 1
                dim_one.append([birth_tup,death_tup])
                dim_one_it += 1
    return dim_zero,dim_one


def pairs_to_barcodes(sc_type):
    #results_dir = '/Users/ananyashah/persistanthomology/tda/tx_barcode.csv'
    if os.path.isfile(filename):
        [dim_zero,dim_one] = parse_csv_to_birth_death(filename)

        dim_zero_lines = mc.LineCollection(dim_zero, linewidths=2)
        dim_one_lines = mc.LineCollection(dim_one, linewidth=2)
        fig, ax = pl.subplots(1, sharex=True)
        #ax[0].add_collection(dim_zero_lines)
        ax.add_collection(dim_one_lines)
        #ax[0].autoscale()
        ax.autoscale()
        #ax[0].set_title("$H_0$", fontsize=20)
        ax.set_title("$H_1$", fontsize=20)
        ya = ax.get_yaxis()
        ya.set_major_locator(MaxNLocator(integer=True))
        ya = ax.get_yaxis()
        ya.set_major_locator(MaxNLocator(integer=True))
        a = ax.get_xticks().tolist()
        if sc_type == 'adj':
            b = list((19-np.asarray(a))*5)
        else:
            b = a
        #ax[0].set_xticklabels(b)
        #ax[0].tick_params(axis='y', which='both', left=False, right=False, labelleft=False)
        ax.set_xticklabels(b)
        ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False)
        if sc_type == 'adj':
            ax.set_xlabel('Strength of Preference', fontsize=20)
        elif sc_type == 'ls':
            ax.set_xlabel('T', fontsize=20)
        else:
            ax.set_xlabel('$\epsilon$', fontsize=20)
            
        pl.tight_layout()
       
        #barcode_dir = '/Users/ananyashah/persistanthomology/tda/tx_barcode.csv'
        fig.savefig(savepath)


        
        pl.close(fig)
    else:
        #logging.warning('No results file for ' + county + ', ' + candidate + ', ' + sc_type)
        logging.warning('No results file')
        
    
# if (len(sys.argv)!=3):
#     print "Wrong number of arguments"
# else:
#     pairs_to_barcodes(sys.argv[1],sys.argv[2])
def main():
    # logging.basicConfig(filename='../logs/barcodes.log', filemode='w', level=logging.WARNING)
    # with open('../full-list') as county_file:
    #     for county in county_file:
    #         county = county.split('\n')[0]
    #         for candidate in ['hillary', 'trump']:
    for sc_type in ['ls','adj','rips','alpha']:
    #for sc_type in ['alpha']:
        pairs_to_barcodes(sc_type)


if __name__ == '__main__':
    main()
## CALCULATING BOTTLENECK DISTANCE
import gudhi as gd

from gudhi import wasserstein
import pandas as pd
import numpy as np

# Load your CSV file (adjust the file path accordingly)
df1 = pd.read_csv('/Users/justinmurri/Gerrymander-Research/topology_analysis/ut_barcode_2020.csv', header=None)
df2 = pd.read_csv('/Users/justinmurri/Gerrymander-Research/topology_analysis/ut_barcode.csv', header=None)

# Convert DataFrame to list of tuples for persistence diagrams
diag1 = [tuple(x) for x in df1.to_numpy()]
diag2 = [tuple(x) for x in df2.to_numpy()]

# Calculate the bottleneck distance
distance = gd.bottleneck_distance(diag1, diag2)
print("Bottleneck distance:", distance)

