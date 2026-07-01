#!/usr/bin/env python
# coding: utf-8

# # Sizing and deciding power solution for mines
# <br>
# 
# **Conceptualization, & Methodology:** [Alexandros Korkovelos](https://github.com/akorkovelos)<br>
# **Code:** [Alexandros Korkovelos](https://github.com/akorkovelos) and [Camilo Ramirez](https://github.com/camiloramirezgo)<br>
# **Funding:** Imperial College London

# ## Import necessary modules
# 
# As part of any modeling exercise in jupyter, the first step requires that the necessary python modules are imported. You may refer to the [requirements.txt]() to check dependencies for this notebook.

# In[22]:


# Import python modules
import geopandas as gpd
import pandas as pd
import pyproj
import numpy as np
import fiona
import time
from geojson import Feature, Point, FeatureCollection
from shapely.geometry import shape, mapping
import scipy.spatial
import json

import rasterio
import rasterio.fill
from rasterstats import zonal_stats

from functools import reduce
from shapely.geometry import Point, Polygon, MultiPoint
from shapely.ops import nearest_points

#import datapane as dp
#!datapane login --token="yourpersonaltoken"
#!datapane login --token="9bde41bfbc4ad14119e32086f9f06d2e5db1d5b8"

import folium
from folium.features import GeoJsonTooltip
import branca.colormap as cm
import os
from IPython.display import display, Markdown, HTML, FileLink, FileLinks

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

import datetime

import warnings
warnings.filterwarnings('ignore')


# In[53]:


## Uncomment to run without the snakemake workflow
#scope = 'country'
#constraint = 'constrained'

#mine_path = r"GIS_data/MiningData/DataFromRaghavAug2025"
#mine_name = f"combined_node_locations_for_energy_conversion_{scope}_{constraint}.gpkg"
#lay_name = "bau_2040_low_min_threshold_metal_tons"
# ## Country scenarios ##
#[bau_2040_low_min_threshold_metal_tons, bau_2040_mid_min_threshold_metal_tons, bau_2040_high_min_threshold_metal_tons, 
#early_refining_2040_low_min_threshold_metal_tons, early_refining_2040_mid_min_threshold_metal_tons, 
#early_refining_2040_high_min_threshold_metal_tons, precursor_2040_low_min_threshold_metal_tons, precursor_2040_mid_min_threshold_metal_tons, 
#precursor_2040_high_min_threshold_metal_tons]
# Region scenarios ##
#[bau_2040_low_max_threshold_metal_tons, bau_2040_mid_max_threshold_metal_tons, bau_2040_high_max_threshold_metal_tons, 
#early_refining_2040_low_max_threshold_metal_tons, early_refining_2040_mid_max_threshold_metal_tons, 
#early_refining_2040_high_max_threshold_metal_tons, precursor_2040_low_max_threshold_metal_tons, precursor_2040_mid_max_threshold_metal_tons,
#precursor_2040_high_max_threshold_metal_tons]

# outpath= "Outputs"

# min_processing_values = "min_processing_values_dict_New.xlsx"

# grid_parameters = 'Grid_Parameters.xlsx'

## Variables to run with snakemake, comment if running with the lines above
scope = snakemake.params.scope
constraint = snakemake.params.constraint

mine_path = snakemake.params.mine_path
mine_name = snakemake.input.mine_name
lay_name = snakemake.params.scenario

outpath = snakemake.params.output_folder

min_processing_values = snakemake.input.min_processing_values

grid_parameters = snakemake.input.grid_parameters


# In[24]:


## Fuction for raster extraction
def processing_raster_bulk(file_name, name, method, mines):
    raster=rasterio.open(file_name)

    mines = zonal_stats(
        mines,
        raster.name,
        stats=[method],
        prefix=name, geojson_out=True, all_touched=True)

    #print(datetime.datetime.now())
    return mines


# In[25]:


# Function to convert geojson to geodataframe
def finalizing_rasters(workspace, clusters, scope, constraint, lay_name):
    output = workspace + f'/{scope}_{constraint}_{lay_name}.geojson'
    with open(output, "w") as dst:
        collection = {
            "type": "FeatureCollection",
            "features": list(clusters)}
        dst.write(json.dumps(collection))

    clusters = gpd.read_file(output)
    os.remove(output)

    #print(datetime.datetime.now())
    return clusters


# In[26]:


## Preparing mining dataframe
def preparing_for_vectors(workspace, mines, crs):   
    mines.crs = {'init' :'epsg:4326'}
    mines = mines.to_crs({ 'init': crs}) 
    points = mines.copy()
    points["geometry"] = points["geometry"].centroid
    #points["lon"] = points.geometry.x
    #points["lat"] = points.geometry.y
    points.to_file(workspace + r'/mines_cp.shp', driver='ESRI Shapefile')
    #print(datetime.datetime.now())    
    return mines


# In[27]:


## Function to extract distance to lines
def processing_lines_bulk(lines, name, admin, crs, workspace, mines):
    #lines=gpd.read_file(file_name)

    lines_clip = gpd.clip(lines, admin)
    lines_clip.crs = {'init' :'epsg:4326'}
    lines_proj=lines_clip.to_crs({ 'init': crs})

    lines_proj.to_file(workspace + r"/" + name + "_proj.shp", driver='ESRI Shapefile')

    line = fiona.open(workspace +  r"/" + name + "_proj.shp")
    firstline = line.next()

    schema = {'geometry' : 'Point', 'properties' : {'id' : 'int'},}
    with fiona.open(workspace + r"/" + name + "_proj_points.shp", "w", "ESRI Shapefile", schema) as output:
        for lines in line:
            if lines["geometry"] is not None:
                first = shape(lines['geometry'])
                length = first.length
                for distance in range(0,int(length),100):
                    point = first.interpolate(distance)
                    output.write({'geometry' :mapping(point), 'properties' : {'id':1}})

    lines_f = fiona.open(workspace + r"/" + name + "_proj_points.shp")
    lines = gpd.read_file(workspace +  r"/" + name + "_proj.shp")
    points = fiona.open(workspace + r'/mines_cp.shp')

    geoms1 = [shape(feat["geometry"]) for feat in lines_f]
    s1 = [np.array((geom.xy[0][0], geom.xy[1][0])) for geom in geoms1]
    s1_arr = np.array(s1)

    geoms2 = [shape(feat["geometry"]) for feat in points]
    s2 = [np.array((geom.xy[0][0], geom.xy[1][0])) for geom in geoms2]
    s2_arr = np.array(s2)

    def do_kdtree(combined_x_y_arrays,points):
        mytree = scipy.spatial.cKDTree(combined_x_y_arrays)
        dist, indexes = mytree.query(points)
        return dist, indexes

    def vector_overlap(vec, settlementfile, column_name):
        vec.drop(vec.columns.difference(["geometry"]), axis=1, inplace=True)
        a = gpd.sjoin(settlementfile, vec, predicate='intersects')
        a[column_name + '2'] = 0
        return a  

    results1, results2 = do_kdtree(s1_arr,s2_arr)

    z=results1.tolist()
    mines[name+'Dist'] = z
    mines[name+'Dist'] = mines[name+'Dist']/1000   

    a = vector_overlap(lines, mines, name+'Dist')

    mines = pd.merge(left = mines, right = a[['id',name+'Dist2']], on='id', how = 'left')
    mines.drop_duplicates(subset ="id", keep = "first", inplace = True) 

    mines.loc[mines[name+'Dist2'] == 0, name+'Dist'] = 0

    del mines[name+'Dist2']
    mines.rename(columns={name+'Dist': name+'Dist_km'}, inplace=True)
    line.close()
    lines_f.close()
    points.close()
    #print(datetime.datetime.now())
    return mines


# In[28]:


## Function to extract distance to points (e.g., SubStations)
def processing_points_bulk(points, name, admin, crs, workspace, mines):

    points_clip = gpd.clip(points, admin)
    points_clip.crs = {'init' :'epsg:4326'}
    points_proj=points_clip.to_crs({ 'init': crs})

    points_proj.to_file(workspace + r"/" + name + "_proj.shp", driver='ESRI Shapefile')

    points_f = fiona.open(workspace + r"/" + name + "_proj.shp")
    points = gpd.read_file(workspace +  r"/" + name + "_proj.shp")
    points2 = fiona.open(workspace + r'/mines_cp.shp')

    geoms1 = [shape(feat["geometry"]) for feat in points_f]
    s1 = [np.array((geom.xy[0][0], geom.xy[1][0])) for geom in geoms1]
    s1_arr = np.array(s1)

    geoms2 = [shape(feat["geometry"]) for feat in points2]
    s2 = [np.array((geom.xy[0][0], geom.xy[1][0])) for geom in geoms2]
    s2_arr = np.array(s2)

    def do_kdtree(combined_x_y_arrays,points):
        mytree = scipy.spatial.cKDTree(combined_x_y_arrays)
        dist, indexes = mytree.query(points)
        return dist, indexes

    def vector_overlap(vec, settlementfile, column_name):
        vec.drop(vec.columns.difference(["geometry"]), axis=1, inplace=True)
        a = gpd.sjoin(settlementfile, vec, predicate='intersects')
        a[column_name + '2'] = 0
        return a  

    results1, results2 = do_kdtree(s1_arr,s2_arr)

    z=results1.tolist()
    mines[name+'Dist'] = z
    mines[name+'Dist'] = mines[name+'Dist']/1000.

    a = vector_overlap(points, mines, name+'Dist')

    mines = pd.merge(left = mines, right = a[['id',name+'Dist2']], on='id', how = 'left')
    mines.drop_duplicates(subset ="id", keep = "first", inplace = True) 

    mines.loc[mines[name+'Dist2'] == 0, name+'Dist'] = 0

    del mines[name+'Dist2']
    #if mg_filter:
    #    del mines['umgid']

    mines.rename(columns={name+'Dist': name+'Dist_km'}, inplace=True)
    points_f.close()
    points2.close()
    #print(datetime.datetime.now())
    return mines


# In[29]:


## Delete all prepping files in directory (this is needed if you want to rerun the extraction)
def delete_files_in_directory(directory_path):
    try:
        for filename in os.listdir(directory_path):
            file_path = os.path.join(directory_path, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
            else:
                print(f"Skipping directory: {file_path}")
        print("Deletion process completed.")
    except Exception as e:
        print(f"An error occurred: {e}")


# In[35]:


def pv_diesel_hybrid(
        bba, 
        bbb, 
        bbc, 
        bbpme, 
        bbprod,
        consumption,
        ghi,  
        diesel_price,
        grid_dist,
        ghi_curve,
        temp,
        start_year,
        end_year,
        pv_cost_factor,
        diesel_cost=325,  # diesel generator capital cost, USD/kWA rated power
        pv_no=1,  # number of PV panel sizes simulated
        diesel_no=1,  # number of diesel generators simulated
        discount_rate=0.138,
):
    n_chg = 0.92  # charge efficiency of battery
    n_dis = 0.92  # discharge efficiency of battery
    lpsp_max = 0.01  # maximum loss of load allowed over the year, in share of kWh ## 0.0001
    battery_cost = 593  # battery capital capital cost, USD/kWh of storage capacity
    pv_cost = 1200 * 1  # PV panel capital cost, USD/kW peak power
    pv_life = 25  # PV panel expected lifetime, years
    diesel_life = 10  # diesel generator expected lifetime, years
    pv_om = 0.015  # annual OM cost of PV panels
    diesel_om = 0.1  # annual OM cost of diesel generator
    k_t = 0.005  # temperature factor of PV panels
    inverter_cost = 230
    inverter_life = 10
    inv_eff = 0.92  # inverter_efficiency
    charge_controller = 0.0001
    sgna = 0.0001 # $/connection/year

    ### Input requirement ###

    ### Use this distance (0.1 --> 100 meters) do "force grid connection in locations that are within this buffer from grid lines
    if grid_dist <= 0.1:
        return list((99e15, 99e15, 99e15, 99e15, 99e15, 99e15, 99e15, 99e15, 
                 99e15, 99e15, 99e15, 99e15, 99e15, consumption*8760/1000))
    else:

        ghi = ghi_curve * ghi * 1000 / ghi_curve.sum()
        hour_numbers = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23) * 365
        dod_max = 0.8  # maximum depth of discharge of battery

        def load_curves(bba, bbb, bbc, bbpme, bbprod, consumption):
            # the values below define the load curve for the five tiers. The values reflect the share of the daily demand
            # expected in each hour of the day (sum of all values for one tier = 1)
            ba_load_curve = [0.988074348, 0.83234137, 0.780348447, 0.895071886, 1.29452897, 1.427317285,
                         1.427143895, 2.036533853, 2.788021073, 3.132621618, 3.398067297, 3.597146625,
                         3.749088177, 3.619622164, 3.645379008, 3.798564636, 4.140905488, 6.288317305,
                         9.012611343, 8.343100334, 6.300316324, 3.931731497, 2.193525721, 1.379620337]

            bb_load_curve = [3.184482155, 2.873016199, 2.769030352, 2.99847723, 3.797391399, 4.062968029, 
                         4.062621248, 5.281401164, 6.784375605, 7.473576694, 8.004468052, 8.402626707, 
                         8.706509811, 8.447577786, 8.499091475, 8.805462731, 9.490144434, 13.78496807, 
                         19.23355614, 17.89453413, 13.80896611, 9.071796452, 5.5953849, 3.967574132]

            bc_load_curve = [8.923873354, 8.047396638, 7.614331638, 7.763438133, 9.507818801, 12.4321089,
                         13.48321774, 14.41446325, 15.87567906, 16.28469545, 17.16546017, 17.7633564,
                         18.49249621, 19.22393746, 19.1473699, 18.37923754, 17.41429094, 23.6968058, 
                         40.54912477, 48.55186439, 44.0975794, 32.05947574, 19.32369079, 11.78828855]

            bpme_load_curve = [0.250823098, 0.250823098, 0.250823098, 0.250823098, 0.250823098, 0.250823098,
                           7.645880133, 18.30034088, 30.36078872, 42.83318642, 49.9405017, 52.93860082,
                           49.93452555, 44.38491667, 35.85872985, 27.40653484, 20.76932651, 32.56118326,
                           62.28781859, 74.50081552, 62.8359663, 36.32711164, 17.17269706, 4.690252421]

            #bprod_load_curve = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
            #                   0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
            #                   0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
            #                   0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
            bprod_load_curve = [consumption] * 24


            ba_load_curve = [i * bba for i in ba_load_curve]
            bb_load_curve = [i * bbb for i in bb_load_curve]
            bc_load_curve = [i * bbc for i in bc_load_curve]
            bpme_load_curve = [i * bbpme for i in bpme_load_curve]
            bprod_load_curve = [i * bbprod for i in bprod_load_curve]

            load_curve = [sum(x) for x in zip(ba_load_curve, bb_load_curve, bc_load_curve, bpme_load_curve, bprod_load_curve )] * 365

            load_curve = [i / 1000 for i in load_curve]

            return np.array(load_curve) 

        load_curve = load_curves(bba, bbb, bbc, bbpme, bbprod, consumption)
        energy_per_hh = (sum(load_curves(bba, bbb, bbc, bbpme, bbprod, consumption)))

        def pv_diesel_capacities(pv_capacity, battery_size, diesel_capacity, pv_no, diesel_no, battery_no):
            dod = np.zeros(shape=(24, battery_no, pv_no, diesel_no))
            battery_use = np.zeros(shape=(24, battery_no, pv_no, diesel_no))  # Stores the amount of battery discharge during the day
            fuel_result = np.zeros(shape=(battery_no, pv_no, diesel_no))
            battery_life = np.zeros(shape=(battery_no, pv_no, diesel_no))
            soc = np.ones(shape=(battery_no, pv_no, diesel_no)) * 0.5
            unmet_demand = np.zeros(shape=(battery_no, pv_no, diesel_no))
            excess_gen = np.zeros(shape=(battery_no, pv_no, diesel_no))  # TODO
            annual_diesel_gen = np.zeros(shape=(battery_no, pv_no, diesel_no))
            dod_max = np.ones(shape=(battery_no, pv_no, diesel_no)) * 0.6

            for i in range(8760):

                # Battery self-discharge (0.02% per hour)
                battery_use[hour_numbers[i], :, :] = 0.0002 * soc
                soc *= 0.9998

                # Calculation of PV gen and net load
                t_cell = temp[i] + 0.0256 * ghi[i]  # PV cell temperature
                pv_gen = pv_capacity * 0.9 * ghi[i] / 1000 * (1 - k_t * (t_cell - 25))  # PV generation in the hour
                net_load = load_curve[hour_numbers[i]] - pv_gen * inv_eff  # remaining load not met by PV panels

                # Dispatchable energy from battery available to meet load
                battery_dispatchable = soc * battery_size * n_dis * inv_eff
                # Energy required to fully charge battery
                battery_chargeable = (1 - soc) * battery_size / n_chg / inv_eff

                # Below is the dispatch strategy for the diesel generator as described in word document

                if 4 < hour_numbers[i] <= 17:
                    # During the morning and day, the batteries are dispatched primarily.
                    # The diesel generator, if needed, is run at the lowest possible capacity

                    # Minimum diesel capacity to cover the net load after batteries.
                    # Diesel genrator limited by lowest possible capacity (40%) and rated capacity
                    min_diesel = np.minimum(
                        np.maximum(net_load - battery_dispatchable, 0.4 * diesel_capacity),
                        diesel_capacity)

                    diesel_gen = np.where(net_load > battery_dispatchable, min_diesel, 0)

                elif 17 > hour_numbers[i] > 23:
                    # During the evening, the diesel generator is dispatched primarily, at max_diesel.
                    # Batteries are dispatched if diesel generation is insufficient.

                    #  Maximum amount of diesel needed to supply load and charge battery
                    # Diesel genrator limited by lowest possible capacity (40%) and rated capacity
                    max_diesel = np.maximum(
                        np.minimum(net_load + battery_chargeable, diesel_capacity),
                        0.4 * diesel_capacity)

                    diesel_gen = np.where(net_load > 0, max_diesel, 0)
                else:
                    # During night, batteries are dispatched primarily.
                    # The diesel generator is used at max_diesel if load is larger than battery capacity

                    #  Maximum amount of diesel needed to supply load and charge battery
                    # Diesel genrator limited by lowest possible capacity (40%) and rated capacity
                    max_diesel = np.maximum(
                        np.minimum(net_load + battery_chargeable, diesel_capacity),
                        0.4 * diesel_capacity)

                    diesel_gen = np.where(net_load > battery_dispatchable, max_diesel, 0)

                fuel_result += np.where(diesel_gen > 0, diesel_capacity * 0.08145 + diesel_gen * 0.246, 0)
                annual_diesel_gen += diesel_gen

                # Reamining load after diesel generator
                net_load = net_load - diesel_gen

                # If diesel generation is used, but is smaller than load, battery is discharged
                soc -= np.where((net_load > 0) & (diesel_gen > 0),
                                net_load / n_dis / inv_eff / battery_size,
                                0)

                # If diesel generation is used, and is larger than load, battery is charged
                soc -= np.where((net_load < 0) & (diesel_gen > 0),
                                net_load * n_chg * inv_eff / battery_size,
                                0)

                # If net load is positive and no diesel is used, battery is discharged
                soc -= np.where((net_load > 0) & (diesel_gen == 0),
                                net_load / n_dis / battery_size,
                                0)

                # If net load is negative, and no diesel has been used, excess PV gen is used to charge battery
                soc -= np.where((net_load < 0) & (diesel_gen == 0),
                                net_load * n_chg / battery_size,
                                0)


                # The amount of battery discharge in the hour is stored (measured in State Of Charge)
                battery_use[hour_numbers[i], :, :] = \
                    np.minimum(np.where(net_load > 0,
                                        net_load / n_dis / battery_size,
                                        0),
                               soc)

                # If State of charge is negative, that means there's demand that could not be met.
                unmet_demand += np.where(soc < 0,
                                         -soc / n_dis * battery_size,
                                         0)
                soc = np.maximum(soc, 0)

                # If State of Charge is larger than 1, that means there was excess PV/diesel generation
                excess_gen += np.where(soc > 1,
                                       (soc - 1) / n_chg * battery_size,
                                       0)
                # TODO
                soc = np.minimum(soc, 1)

                dod[hour_numbers[i], :, :] = 1 - soc  # The depth of discharge in every hour of the day is stored
                if hour_numbers[i] == 23:  # The battery wear during the last day is calculated
                    battery_used = np.where(dod.max(axis=0) > 0, 1, 0)
                    battery_life += battery_use.sum(axis=0) / (
                            531.52764 * np.maximum(0.1, dod.max(axis=0) * dod_max) ** -1.12297) * battery_used

            condition = unmet_demand / energy_per_hh  # LPSP is calculated
            excess_gen = excess_gen / energy_per_hh
            battery_life = np.round(1 / battery_life)
            diesel_share = annual_diesel_gen / energy_per_hh

            return diesel_share, battery_life, condition, fuel_result, excess_gen

        # This section creates the range of PV capacities, diesel capacities and battery sizes to be simulated
        ref = 5 * load_curve[19]

        battery_sizes = [energy_per_hh / 365]
        pv_caps = []
        diesel_caps = []
        diesel_extend = np.ones(pv_no)
        pv_extend = np.ones(diesel_no)

        for i in range(pv_no):
            pv_caps.append(ref * (pv_no - i) / pv_no)

        for j in range(diesel_no):
            diesel_caps.append(j * max(load_curve) / diesel_no)

        pv_caps = np.outer(np.array(pv_caps), pv_extend)
        diesel_caps = np.outer(diesel_extend, np.array(diesel_caps))

        # This section creates 2d-arrays to store information on PV capacities, diesel capacities, battery sizes,
        # fuel usage, battery life and LPSP

        battery_size = np.ones((len(battery_sizes), pv_no, diesel_no))
        pv_panel_size = np.zeros((len(battery_sizes), pv_no, diesel_no))
        diesel_capacity = np.zeros((len(battery_sizes), pv_no, diesel_no))

        for j in range(len(battery_sizes)):
            battery_size[j, :, :] *= battery_sizes[j]
            pv_panel_size[j, :, :] = pv_caps
            diesel_capacity[j, :, :] = diesel_caps

        # For the number of diesel, pv and battery capacities the lpsp, battery lifetime, fuel usage and LPSP is calculated
        diesel_share, battery_life, lpsp, fuel_usage, excess_gen = \
            pv_diesel_capacities(pv_panel_size, battery_size, diesel_capacity, pv_no, diesel_no, len(battery_sizes))
        battery_life = np.minimum(20, battery_life)

        def calculate_hybrid_lcoe(diesel_price):
            # Necessary information for calculation of LCOE is defined
            project_life = end_year - start_year
            generation = np.ones(project_life) * energy_per_hh
            generation[0] = 0

            # Calculate LCOE
            sum_costs = np.zeros((len(battery_sizes), pv_no, diesel_no))
            sum_el_gen = np.zeros((len(battery_sizes), pv_no, diesel_no))
            investment = np.zeros((len(battery_sizes), pv_no, diesel_no))
            gen_opex = np.zeros((len(battery_sizes), pv_no, diesel_no))
            sgna_opex = np.zeros((len(battery_sizes), pv_no, diesel_no))

            for year in range(project_life + 1):
                salvage = np.zeros((len(battery_sizes), pv_no, diesel_no))

                fuel_costs = fuel_usage * diesel_price
                om_costs = (pv_panel_size * (pv_cost + charge_controller) * pv_om + diesel_capacity * diesel_cost * diesel_om)
                sgna_costs = (bba+bbb+bbc+bbpme+bbprod)*sgna
                om_costsy1 = (pv_panel_size * (pv_cost + charge_controller) * pv_om + diesel_capacity * diesel_cost * diesel_om)[0][0][0]
                sgna_costsy1 = (bba+bbb+bbc+bbpme+bbprod)*sgna

                #print (om_costsy1, sgna_costsy1)

                inverter_investment = np.where(year % inverter_life == 0, max(load_curve) * inverter_cost, 0)
                diesel_investment = np.where(year % diesel_life == 0, diesel_capacity * diesel_cost, 0)
                pv_investment = np.where(year % pv_life == 0, pv_panel_size * (pv_cost + charge_controller), 0)
                battery_investment = np.where(year % battery_life == 0, battery_size * battery_cost / dod_max, 0)  # TODO Include dod_max here?

                if year == project_life:
                    salvage = (1 - (project_life % battery_life) / battery_life) * battery_cost * battery_size / dod_max + \
                              (1 - (project_life % diesel_life) / diesel_life) * diesel_capacity * diesel_cost + \
                              (1 - (project_life % pv_life) / pv_life) * pv_panel_size * (pv_cost + charge_controller) + \
                              (1 - (project_life % inverter_life) / inverter_life) * max(load_curve) * inverter_cost

                #investment += diesel_investment + pv_investment + battery_investment + inverter_investment - salvage
                investment += (diesel_investment + pv_investment + battery_investment + inverter_investment - salvage) / ((1 + discount_rate) ** year)

                #gen_opex and sgna opex
                gen_opex += om_costs / ((1 + discount_rate) ** year)
                sgna_opex += sgna_costs / ((1 + discount_rate) ** year)

                sum_costs += (fuel_costs + om_costs + sgna_costs + diesel_investment + pv_investment + battery_investment + inverter_investment - salvage) / ((1 + discount_rate) ** year)

                if year > 0:
                    sum_el_gen += energy_per_hh / ((1 + discount_rate) ** year)

            return sum_costs / sum_el_gen, investment, gen_opex, om_costsy1, sgna_opex, sgna_costsy1, sum_costs, fuel_usage     ### use "sum_costs" to get the NPV of all lifetime costs; change to "investment" to get the CAPEX (second option discounted)

        diesel_limit = 1

        min_lcoe_range = []
        investment_range = []
        opex_gen_range = []
        opex_geny1_range = []
        opex_sgna_range = []
        opex_sgnay1_range = []
        npv_costs_range = []
        capacity_range = []
        ren_share_range = []
        #diesel_cap_range = []
        bat_size_range = []
        fuel_usage_range = []

        diesel_range = [diesel_price]

        for d in diesel_range:

            lcoe, investment, gen_opex, gen_opexy1, sgna_opex, sgna_opexy1, npv_costs, fuel_u = calculate_hybrid_lcoe(d)
            lcoe = np.where(lpsp > lpsp_max, 999999, lcoe)
            lcoe = np.where(diesel_share > diesel_limit, 999999, lcoe)

            min_lcoe = np.min(lcoe)
            min_lcoe_combination = np.unravel_index(np.argmin(lcoe, axis=None), lcoe.shape)
            ren_share = 1 - diesel_share[min_lcoe_combination]
            capacity = pv_panel_size[min_lcoe_combination] + diesel_capacity[min_lcoe_combination]
            ren_capacity = pv_panel_size[min_lcoe_combination]
            diesel_capacity = diesel_capacity[min_lcoe_combination]
            bat_size = battery_size[min_lcoe_combination]
            excess_gen = excess_gen[min_lcoe_combination]
            #fu = fu[min_lcoe_combination]

            min_lcoe_range.append(min_lcoe)
            investment_range.append(investment[min_lcoe_combination])
            opex_gen_range.append(gen_opex[min_lcoe_combination])
            opex_geny1_range.append(gen_opexy1)
            opex_sgna_range.append(sgna_opex[min_lcoe_combination])
            opex_sgnay1_range.append(sgna_opexy1)
            npv_costs_range.append(npv_costs[min_lcoe_combination])
            capacity_range.append(capacity)
            ren_share_range.append(ren_share)
            #diesel_cap_range.append(diesel_capacity)
            bat_size_range.append(bat_size)
            fuel_usage_range.append(fuel_u[min_lcoe_combination])

            lcoe_hmg = round(min_lcoe_range[0], 4)
            inv_hmg = round(investment_range[0], 2)
            opexgen_hmg = round(opex_gen_range[0], 2)
            opexgeny1_hmg = round(opex_geny1_range[0], 2)
            opexsgna_hmg = round(opex_sgna_range[0], 2)
            opexsgnay1_hmg = round(opex_sgnay1_range[0], 2)
            npv_hmg = round(npv_costs_range[0], 2)
            cap_hmg = round(capacity_range[0], 2)
            ren_share_hmg = round(ren_share_range[0], 3)
            bat_size_hmg = round(bat_size_range[0], 2)
            fu_hmg = round(fuel_usage_range[0], 2)

        #return min_lcoe_range, investment_range, capacity_range, ren_capacity, diesel_capacity, ren_share_range, excess_gen.
        return list((lcoe_hmg, inv_hmg, opexgen_hmg, opexgeny1_hmg, opexsgna_hmg, opexsgnay1_hmg, npv_hmg, cap_hmg, 
                     round(ren_capacity,2), round(diesel_capacity,3), ren_share_hmg, bat_size_hmg, fu_hmg, round(energy_per_hh,2)))


# In[36]:


def MG_diesel_fuel_cost(diesel_price, travel_hours):
    '''
    Szabo formula is: p = (p_d + 2*p_d*consumption*time/volume)*(1/mu)*(1/LHVd)

    '''
    diesel_truck_consumption = 14
    diesel_truck_volume = 300
    LHV_DIESEL = 9.9445485
    efficiency = 0.33

    fuel_cost = (diesel_price + 
                 (2 * diesel_price * diesel_truck_consumption * travel_hours / diesel_truck_volume / LHV_DIESEL) / efficiency)

    return fuel_cost


# In[37]:


# Function to calculate demand_country for the new format
def calculate_demand_country(row):
    total_demand = 0
    country_code = row['iso3']  # or row['country'] if you use full name

    for (c, mineral, stage_cut), energy_intensity in result_dict.items():
        if c != country_code:
            continue
        production_col = f"{mineral}_production_tons_{stage_cut}_in_country"
        if production_col in row:
            total_demand += (row[production_col] * 1000) * energy_intensity
    return total_demand

# Function to calculate demand_country for the new format
def calculate_demand_region(row):
    total_demand = 0
    country_code = row['iso3']  # or row['country'] if you use full name

    for (c, mineral, stage_cut), energy_intensity in result_dict.items():
        if c != country_code:
            continue
        production_col = f"{mineral}_production_tons_{stage_cut}_in_region"
        if production_col in row:
            total_demand += (row[production_col] * 1000) * energy_intensity
    return total_demand


# In[ ]:


def long_to_wide_format(df):
    df = df.copy()
    stages = df['processing_stage'].unique()
    for mineral in df['reference_mineral'].unique():
        for stage in stages:
            prod_name = f'{mineral}_production_tons_{stage}_in_{scope}'
            df[prod_name] = 0
            df.loc[(df['reference_mineral']==mineral) & (df['processing_stage']==stage), prod_name] = df.loc[(df['reference_mineral']==mineral) & (df['processing_stage']==stage), 'production_tonnes_for_water'].astype(float)

    agg_columns = {'iso3': 'first'}
    agg_columns.update({col: 'sum' for col in df.columns[df.columns.str.contains('tons')]})
    agg_columns.update({'water_intensity_m3_per_kg': 'mean', 'water_usage_m3': 'sum'})
    df['water_intensity_m3_per_kg'] = df['water_intensity_m3_per_kg'].astype(float)
    df['water_usage_m3'] = df['water_usage_m3'].astype(float)
    dff = df.groupby('id').agg(agg_columns)
    dff.replace(0, float('NaN'), inplace=True)
    dff.dropna(how='all', axis=1, inplace=True)
    dff.replace(float('NaN'), 0, inplace=True)
    return dff


# In[38]:


#countries = ["Angola", "Botswana", "Burundi", "DRC", "Kenya", "Madagascar", "Malawi", 
#             "Mozambique", "Namibia", "South_Africa", "Tanzania", "Uganda", "Zambia", "Zimbabwe"]


#['AGO', 'BWA', 'BDI', 'COD', 'KEN', 'MDG', 'MWI, 'MOZ', 'NAM', ZAF', 'TZA', 'UGA', 'ZMB', ZWE']
#[ao, bw, bi, cd, ke, mg, mw, mz, na, za, tz, ug, zm, zw ]


# In[39]:


##coordinates 
## Angola -> 32734
## Botswana -> 32735
## Burundi -> 32735
## DRC -> 32734
## Kenya -> 32736
## Madagascar -> 32739
## Malawi -> 32736
## Mozambique -> 32736
## Namibia -> 32734
## South_Africa -> 32734
## Tanzania -> 32735
## Uganda -> 32735
## Zambia -> 32735
## Zimbabwe -> 32736


# In[40]:


countries = ["Angola", "Botswana", "Burundi", "DRC", "Kenya", "Madagascar", "Malawi", 
             "Mozambique", "Namibia", "South_Africa", "Tanzania", "Uganda", "Zambia", "Zimbabwe"]

codes_3_letter = ['AGO', 'BWA', 'BDI', 'COD', 'KEN', 'MDG', 'MWI', 'MOZ', 'NAM', 'ZAF', 'TZA', 'UGA', 'ZMB', 'ZWE']
codes_2_letter = ['ao', 'bw', 'bi', 'cd', 'ke', 'mg', 'mw', 'mz', 'na', 'za', 'tz', 'ug', 'zm', 'zw']
coordinates = [32734, 32735, 32735, 32734, 32736, 32739, 32736, 32736, 32734, 32734, 32735, 32735, 32735, 32736]

country_dict = {}

for i in range(len(countries)):
    country_dict[countries[i]] = {
        '3_letter_code': codes_3_letter[i],
        '2_letter_code': codes_2_letter[i],
        'coordinate': coordinates[i]
    }


# In[ ]:


for country in countries:
    start = time.time()
    cntry = country
    cntryc = country_dict[country]["2_letter_code"]
    cntryiso = country_dict[country]["3_letter_code"]

    ## Coordinate and projection systems
    crs_WGS84 = pyproj.CRS("EPSG:4326")    # Originan WGS84 coordinate system
    crs_proj = pyproj.CRS("EPSG:{}".format(country_dict[country]["coordinate"]))    # Projection system for the selected country -- see http://epsg.io/ for more info

    # Define path and name of the file
    admin_path = r"GIS_data/{}".format(cntry)
    admin_name = "{}_admin0.gpkg".format(cntry)

    #############!!!!!!
    ## UPDATE per scenario run

    # Define path and name of the file
    # mine_path = r"GIS_data/MiningData/DataFromRaghavAug2025"
    # mine_name = "combined_node_locations_for_energy_conversion_region_unconstrained.gpkg"
    # lay_name = "precursor_2040_mid_max_threshold_metal_tons"

    #############!!!!!!

    # Define path and name of the file
    HV_path = r"GIS_data/{}".format(cntry)
    HV_name = "HV_lines.gpkg"
    #HV_name = "ZMB_transmission-lines21.geojson"

    ## Define path and name of the file
    #MV_path = r"C:/Users/alexl/Dropbox/Self-employment/SEforALL/Work/Zambia/Work/GIS_data/WRI"
    #MV_name = "ZMB_distribution-lines21.geojson"

    ## Define path and name of the file
    #sub_path = r"C:/Users/alexl/Dropbox/Self-employment/SEforALL/Work/Zambia/Work/GIS_data/FromShakySherpa/Zambia_finaldatabase/Data/2-Infrastructure/ZESCO"
    #sub_name = "HVMVsubstation.shp"

    # Define path and name of the file
    sub_path = r"GIS_data/{}".format(cntry)
    sub_name = "substations.gpkg"

    # GHI raster layer to be used
    ghi = r"GIS_data/{}/GHI.tif".format(cntry)
    #ghi = r"C:/Users/alexl/Dropbox/Self-employment/Imperial work/Mineral Work/GIS_data/SSSA_GHI.tif"

    # Traveltime (in minutes) raster layer to be used
    traveltime = r"GIS_data/{}/accessibility_2015.tif".format(cntry)
    #traveltime = r"C:/Users/alexl/Dropbox/Self-employment/Imperial work/Mineral Work/GIS_data/SSSA_travel_time.tif"

    # Path of solar resource data
    path = r"GIS_data/{}/{}-2-pv.csv".format(cntry, cntryc)

    # Path of result files
    # outpath= r"Outputs"
    os.makedirs(outpath, exist_ok=True)

    outpathscen = os.path.join(outpath, 'Results', '_'.join([lay_name, scope, constraint]))
    os.makedirs(outpathscen, exist_ok=True)

    def read_environmental_data(path):
        ghi_curve = pd.read_csv(path, usecols=[3], skiprows=3).values  # * 1000
        ghi_curve = ghi_curve[341879:350643]
        temp = pd.read_csv(path, usecols=[2], skiprows=3).values
        temp = temp[341879:350643]

        return ghi_curve, temp

    ghi_curve, temp = read_environmental_data(path)


    # Create a new geo-dataframe
    admin_gdf = gpd.read_file(admin_path + "//" + admin_name)

    # Create a new geo-dataframe
    mine_gdf = gpd.read_file(mine_name)
    mine_gdf = long_to_wide_format(mine_gdf) # change format from long to wide
    mines_locations = gpd.read_file(f'GIS_data/MiningData/Locations/combined_node_locations_for_energy_conversion_{scope}_{constraint}.gpkg',
                                    layer=lay_name)
    mine_gdf = mine_gdf.merge(mines_locations[['id', 'geometry']], on='id')
    mine_gdf.set_geometry('geometry')
    mine_gdf.crs = 4326

    mine_gdf = mine_gdf[mine_gdf['iso3'] == cntryiso]

    if not mine_gdf.empty:

        HV_gdf = gpd.read_file(HV_path + "//" + HV_name)
        #MV_gdf = gpd.read_file(MV_path + "//" + MV_name)
        subs_gdf = gpd.read_file(sub_path + "//" + sub_name)

        mine_gdf = processing_raster_bulk(ghi,"GHI","mean",mine_gdf)
        mine_gdf = processing_raster_bulk(traveltime,"TravelT","mean",mine_gdf)

        ## Run this after raster extraction is complete
        mine_gdf = finalizing_rasters(outpathscen, mine_gdf, scope, constraint, lay_name)

        mine_gdf = preparing_for_vectors(outpathscen, mine_gdf, crs_proj)
        mine_gdf = processing_lines_bulk(HV_gdf, "HV", admin_gdf, crs_proj, outpathscen, mine_gdf)

        mine_gdf["avg_diesel_price"] = 1
        mine_gdf["TravelTmean"] /= 60     ## Convertin travel time from min to hours

        mine_gdf["MG_diesel_cost"] = mine_gdf.apply(lambda row: MG_diesel_fuel_cost(row["avg_diesel_price"], row["TravelTmean"]), axis=1)

        #############!!!!!!
        ## UPDATE per scenario run

        # Read unique values dictionary from an Excel file
        unique_values_mine_gdf = pd.read_excel(min_processing_values)
        # Convert the DataFrame to a dictionary with mineral as key and stage_cut, mining_energy_intensity, and processing_energy_intensity as values
        result_dict = {(row['isocc'], row['mineral'], row['stage_cut']): row['processing_energy_intensity'] for index, row in unique_values_mine_gdf.iterrows()}


        # Apply the function to each row
        if scope == 'country':
            mine_gdf['demand_country'] = mine_gdf.apply(calculate_demand_country, axis=1)
            mine_gdf["Consumption"] = mine_gdf["demand_country"]*1000/8760
        else:
            mine_gdf['demand_region'] = mine_gdf.apply(calculate_demand_region, axis=1)
            mine_gdf["Consumption"] = mine_gdf["demand_region"]*1000/8760

        #############!!!!!!

        mine_gdf["bba"] = 0
        mine_gdf["bbb"] = 0
        mine_gdf["bbc"] = 0
        mine_gdf["bbpme"] = 0
        mine_gdf["bbprod"] = 1

        mine_gdf["hybrids"] = mine_gdf.apply(lambda row: pv_diesel_hybrid(row['bba'],
                                                                          row['bbb'],
                                                                          row['bbc'],
                                                                          row['bbpme'],
                                                                          row['bbprod'],
                                                                          row["Consumption"],
                                                                          row["GHImean"],
                                                                          row["MG_diesel_cost"],
                                                                          row["distance_to_grid_km"],
                                                                          ghi_curve,
                                                                          temp,
                                                                          2023,
                                                                          2040,
                                                                          1, 
                                                                          diesel_cost=325,
                                                                          pv_no=20,
                                                                          diesel_no=20,
                                                                          discount_rate=0.10), axis=1)


        mine_gdf[['HGM_lcoe','HMG_Inv', 'HMG_GenOpex', 'HMG_GenOpex_y', 'HMG_SGnAOpex', 'HMG_SGnAOpex_y',
                  'HMG_npv_cost', 'HMG_cap', 'HMG_ren_cap', 'HMG_dl_cap', 'HMG_ren_share', 'HMG_bat_size', 'HMG_fuel_usage', 
                  'Est_dem_kWh_year']] = pd.DataFrame(mine_gdf.hybrids.tolist(), index= mine_gdf.index)

        mine_gdf['Peak_Load_kW'] = mine_gdf["Est_dem_kWh_year"]/8760    # in kW
        #mine_gdf['Peak_Load_kW'] = mine_gdf["Consumption"]/8760    # in kW
        mine_gdf['Substation_Capacity_kW'] = 100000000 # in kW

        #############!!!!!!
        ## UPDATE per scenario run

        # Load the Excel file containing the grid parameters
        xls = pd.ExcelFile(grid_parameters)

        # Load the 'Climate GEP' sheet into a DataFrame
        grid_df = pd.read_excel(grid_parameters, sheet_name='CriticalMineral')

        #############!!!!!!

        # Correct any potential leading/trailing whitespace in column names
        grid_df.columns = grid_df.columns.str.strip()


        # Create the dictionary with 'Country' as keys and the specified columns as values
        grid_data_dict = grid_df.set_index('Country_param')[grid_df.columns[1:]].T.to_dict()

        #grid_data_dict = grid_df.set_index('Region')[['Generating Cost ($/kWh)', 'Generating Capex ($/kW)', 'Emission factor (gCO2eq/kWh)']].T.to_dict()

        cntry_capex = cntryiso + "_" + "Average Generating Capex ($/KW)"
        cntry_lcoe = cntryiso + "_" + "Average Generating Cost ($/kWh)"
        cntry_emissions = cntryiso + "_" + "Country-level emission factor (Reference Scenario) gCO2eq/kWh"

        scenario = lay_name + "_" + mine_name.split(".")[0].split("conversion_")[1]


        # Define grid parameters
        line_loss_percent = 5.0  # Line loss percentage
        cost_per_km = 20000.0  # Cost per km in $
        #grid_cap_cost = 2500.0  # Indicative capacity cost per additional kW of centralized grid
        grid_gen_cost = grid_data_dict[cntry_lcoe][scenario] # Indicative generating cost in $/kWh of centralized grid
        project_life = (2043 - 2023) + 1
        #reinvest_year = 0
        step = 0
        discount_rate=0.10
        tech_life = 30
        om_of_td_lines = 0.02
        om_costs = 0.02
        grid_capacity_investment = grid_data_dict[cntry_capex][scenario]  ## $/kW
        grid_ems_factor = grid_data_dict[cntry_emissions][scenario]   ## gCO2eq/kWh
        diesel_ems_factor = 704     ## gCO2eq/kWh
        #effective_load_kw = 2.558401*1.2
        #generation_per_year = 22411.59
        #peak_load = 2.558401
        #fuel_cost = 0.056
        #td_investment_cost = 2250

        def calculate_grid_costs(row):
            generation_per_year = pd.Series(row['Est_dem_kWh_year'])
            if row['Est_dem_kWh_year'] == 0:
                return "NaN", "NaN", "NaN", "NaN"
            else:
                peak_load = pd.Series(row['Peak_Load_kW'])
                td_investment_cost = pd.Series(row['HVDist_km'] * cost_per_km)  ##SubStDist_km 
                installed_capacity = row['Peak_Load_kW'] - ((line_loss_percent / 100) * row['Peak_Load_kW'])
                cap_cost = td_investment_cost * 0
                capital_investment = installed_capacity * cap_cost
                td_om_cost = td_investment_cost * om_of_td_lines
                total_om_cost = td_om_cost + (cap_cost * om_costs * installed_capacity)
                total_investment_cost = td_investment_cost + capital_investment

                # If the technology life is less than the project life, we will have to invest twice to buy it again
                if tech_life + step < project_life:
                    reinvest_year = tech_life + step
                else:
                    reinvest_year = 0

                year = np.arange(project_life)
                generation_per_year = pd.Series(generation_per_year) ## Est_dem_kWh_year
                el_gen = np.outer(np.asarray(generation_per_year), np.ones(project_life))

                for s in range(step):
                    el_gen[:, s] = 0
                discount_factor = (1 + discount_rate) ** year

                investments = np.zeros(project_life)
                investments[step] = 1

                # Calculate the year of re-investment if tech_life is smaller than project life
                if reinvest_year:
                    investments[reinvest_year] = 1
                investments = np.outer(total_investment_cost, investments)

                grid_capacity_investments = np.zeros(project_life)
                grid_capacity_investments[step] = 1

                # Calculate the year of re-investment if tech_life is smaller than project life
                if reinvest_year:
                    grid_capacity_investments[reinvest_year] = 1
                grid_capacity_investments = np.outer(peak_load * grid_capacity_investment, grid_capacity_investments)

                # Calculate salvage value if tech_life is bigger than project life
                salvage = np.zeros(project_life)
                if reinvest_year > 0:
                    used_life = (project_life - step) - tech_life
                else:
                    used_life = project_life - step - 1
                salvage[-1] = 1
                salvage = np.outer(total_investment_cost * (1 - used_life / tech_life), salvage)

                operation_and_maintenance = np.ones(project_life)
                for s in range(step):
                    operation_and_maintenance[s] = 0
                operation_and_maintenance = np.outer(total_om_cost, operation_and_maintenance)

                fuel = np.outer(np.asarray(generation_per_year), np.zeros(project_life))
                for p in range(project_life):
                    fuel[:, p] = el_gen[:, p] * grid_gen_cost

                discounted_investments = investments / discount_factor
                dicounted_grid_capacity_investments = grid_capacity_investments / discount_factor
                investment_cost = np.sum(discounted_investments, axis=1) + np.sum(dicounted_grid_capacity_investments, axis=1)
                discounted_costs = (investments + operation_and_maintenance + fuel - salvage) / discount_factor

                discounted_generation = el_gen / discount_factor
                lcoe = np.sum(discounted_costs, axis=1) / np.sum(discounted_generation, axis=1)
                lcoe = pd.DataFrame(lcoe[:, np.newaxis])
                investment_cost = pd.DataFrame(investment_cost[:, np.newaxis])
                grid_capacity_usage = installed_capacity / row['Substation_Capacity_kW']

                return installed_capacity, investment_cost[0][0], lcoe[0][0], grid_capacity_usage

            # Function to calculate feasibility, cost, grid capacity usage, and decision for each site
        def calculate_feasibility_and_decision(row):
            #line_loss_kw = (line_loss_percent / 100) * row['Peak_Load_kW']  # in kW
            #effective_load_kw = row['Peak_Load_kW'] - line_loss_kw  # in kW
            #dist_cost = row['SubStDist_km'] * cost_per_km  # Calculate cost in $
            #cap_cost = effective_load_kw * grid_capacity_investment # Calculate cost in $

            #mine_gdf['Est_grid_Capacity_kW'], mine_gdf['Grid_Cost_USD'], mine_gdf['Est_grid_lcoe_$perkWh'], mine_gdf['grid_capacity_usage'] = zip(*mine_gdf.apply(calculate_grid_costs, axis=1))
            #mine_gdf["grid_capacity_usage"] = mine_gdf.apply(lambda row: (row['Est_grid_Capacity_kW'] / row['Substation_Capacity_kW']), axis=1)
            #grid_capacity_usage = (row['Est_grid_Capacity_kW']) / )row['Substation_Capacity_kW'])  # Grid capacity usage as a fraction

            #return row['Est_grid_Capacity_kW'], row['Grid_Cost_USD'], row['Est_grid_lcoe_$perkWh'],row["grid_capacity_usage"] 
            # Calculate the cost of connecting to the grid
            #grid_cost = dist_cost + cap_cost
            #grid_lcoe = grid_gen_cost + 0.1


            est_capacity, grid_cost, est_lcoe, grid_capacity_usage = calculate_grid_costs(row)

            if (grid_capacity_usage == "NaN"):
                return pd.Series({
                    'Grid_Cost_USD': "NaN",
                    'Grid_Capacity': "NaN",
                    'Grid_lcoe': "NaN",
                    'sub_cap_utilization': "NaN",
                    'Decision': "NaN",
                    'Final_Investment_USD': "NaN",
                    'Req_Capacity_kW': "NaN",
                    'Est_lcoe_$perkWh': "NaN",
                    'Est_emiss_tCO2eq': "NaN"
                })
            elif (grid_capacity_usage < 0.5) and (row["HMG_Inv"] > grid_cost):
                return pd.Series({
                    'Grid_Cost_USD': grid_cost,
                    'Grid_Capacity': est_capacity,
                    'Grid_lcoe': est_lcoe,
                    'sub_cap_utilization': grid_capacity_usage,
                    'Decision': 'Grid Connection',
                    'Final_Investment_USD': grid_cost,
                    'Req_Capacity_kW': est_capacity,
                    'Est_lcoe_$perkWh': est_lcoe,
                    'Est_emiss_tCO2eq': row["Consumption"]*grid_ems_factor/1000000
                })
            else:
                return pd.Series({
                    'Grid_Cost_USD': grid_cost,
                    'Grid_Capacity': est_capacity,
                    'Grid_lcoe': est_lcoe,
                    'sub_cap_utilization': grid_capacity_usage,
                    'Decision': 'Off-Grid',
                    'Final_Investment_USD': row["HMG_Inv"],
                    'Req_Capacity_kW': row["HMG_cap"],
                    'Est_lcoe_$perkWh': row["HGM_lcoe"],
                    'Est_emiss_tCO2eq': row["Consumption"]*(1-row["HMG_ren_share"])*diesel_ems_factor/1000000
                })


         # Apply the function to each row and update the DataFrame
        mine_gdf[['Grid_Cost_USD', 'Grid_est_cap_kW', 'Grid_est_lcoe', 'Sub_cap_util',
                  'Decision', 'Final_Investment_USD', 'Req_Capacity_kW', 'Est_lcoe_$perkWh', 'Emissions_tCO2eq']] = mine_gdf.apply(
            calculate_feasibility_and_decision,
            axis=1)

        # outpathscen = os.path.join(outpath, 'Results', '_'.join([lay_name, scope, constraint]))
        # os.makedirs(outpathscen, exist_ok=True)

        # Normal filename generation
        if cntry == "South_Africa":
            # Shortened filename for South Africa to avoid path length issues
            short_scenario = scenario[:40]  # or any shorter fixed name if preferred
            cntry = "SA"

        #mine_gdf.to_csv(os.path.join(outpath,r"{}-country_2023_75_max.csv").format(cntry), index=False)
        mine_gdf.to_csv(os.path.join(outpathscen, r"{}-{}.csv").format(cntry, scenario), index=False)

        end = time.time()
        print(country, (end - start)/60, "min")



# In[ ]:


# Define path and name of the file
#mine_path = r"C:/Users/alexl/Dropbox/Self-employment/Imperial work/Mineral Work/GIS_data/MiningData/DataFromRaghavJan2025"
#mine_name = "combined_node_locations_for_energy_conversion_country_unconstrained.gpkg"
#lay_name = "2022_baseline"
# Create a new geo-dataframe
mine_gdf = gpd.read_file(mine_path + "//" + mine_name, layer=lay_name)


# In[ ]:


mine_gdf["iso3"].value_counts(), mine_gdf.shape[0]


# In[ ]:


def merge_csv_files(directory, keyword):
    # List to hold DataFrames
    dataframes = []

    # Iterate over files in the specified directory
    for filename in os.listdir(directory):
        # Check if the file contains the keyword and is a CSV file
        if keyword in filename and filename.endswith(".csv"):
            filepath = os.path.join(directory, filename)
            # Read the CSV file into a DataFrame and add it to the list
            df = pd.read_csv(filepath)
            dataframes.append(df)

    # Concatenate all DataFrames in the list into a single DataFrame
    if dataframes:
        merged_df = pd.concat(dataframes, ignore_index=True)
        return merged_df
    else:
        print("No files found with the specified keyword.")
        return None

## Merge files in outpath file
merged_df = merge_csv_files(outpathscen, scenario)


# In[ ]:


merged_df["iso3"].value_counts(), merged_df.shape[0]


# In[ ]:


mine_gdf = mine_gdf.merge(merged_df[['Decision', 'Final_Investment_USD', 'Req_Capacity_kW',
                                         'Est_lcoe_$perkWh', 'Emissions_tCO2eq', 'id']], 
                          how="left", 
                          on="id")


# In[ ]:


mine_gdf.to_file(os.path.join(outpathscen,r"{}.gpkg").format(scenario), driver="GPKG" )
merged_df.to_csv(os.path.join(outpathscen,r"{}.csv").format(scenario), index=False)


# In[ ]:




