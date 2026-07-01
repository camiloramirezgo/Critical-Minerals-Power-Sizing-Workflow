
import glob
# CONSTRAINT = ['constrained', 'unconstrained']
# SCENARIOS = {'country': ["bau_2040_low_min_threshold_metal_tons",
                         # "bau_2040_mid_min_threshold_metal_tons",
                         # "bau_2040_high_min_threshold_metal_tons",
                         # "early_refining_2040_low_min_threshold_metal_tons",
                         # "early_refining_2040_mid_min_threshold_metal_tons",
                         # "early_refining_2040_high_min_threshold_metal_tons",
                         # "precursor_2040_low_min_threshold_metal_tons",
                         # "precursor_2040_mid_min_threshold_metal_tons",
                         # "precursor_2040_high_min_threshold_metal_tons"
                        # ],
             # 'region': ["bau_2040_low_max_threshold_metal_tons",
                        # "bau_2040_mid_max_threshold_metal_tons",
                        # "bau_2040_high_max_threshold_metal_tons",
                        # "early_refining_2040_low_max_threshold_metal_tons",
                        # "early_refining_2040_mid_max_threshold_metal_tons",
                        # "early_refining_2040_high_max_threshold_metal_tons",
                        # "precursor_2040_low_max_threshold_metal_tons",
                        # "precursor_2040_mid_max_threshold_metal_tons",
                        # "precursor_2040_high_max_threshold_metal_tons"
                       # ]}


OUTPUT_FOLDER = 'OutputsJan2026'
MINE_PATH = r'GIS_data/MiningData/water/water_usage_by_location'

CONSTRAINT = ['constrained', 'unconstrained']

layers = glob.glob(f'GIS_data/MiningData/water/water_usage_by_location/*')
SCENARIOS = {'country': [], 'region': []}
files = []
for layer in layers:
    name = layer.split('/')[-1].replace('combined_water_', '') .replace('.csv', '')
    scope = name.split('_')[0]
    constraint = name.split('_')[1]
    scenario = '_'.join(name.split('_')[2:])
    if 'baseline' in scenario:
        if constraint == 'constrained':
            continue
    SCENARIOS[scope].append(scenario)
    files.append(f"{OUTPUT_FOLDER}/Final_Output_per_scenario/{scenario}_{scope}_{constraint}.csv")

rule all:
    input:
        tech_scenario_comparison = f'{OUTPUT_FOLDER}/Summaries/tech_scenario_comparison.xlsx',
        all_scenario_comparison = f'{OUTPUT_FOLDER}/Summaries/all_scenarios_comparison_combined.xlsx'

rule mining_power_sizing:
    input:
        mine_name = f"{MINE_PATH}/combined_water_{{scope}}_{{constraint}}_{{scenario}}.csv",
        min_processing_values = "min_processing_values_dict_New.xlsx",
        grid_parameters = 'Jan_26_GridParameters_updatedheadings.xlsx'
    params:
        scope = '{scope}',
        constraint = '{constraint}',
        mine_path = '.',
        scenario = '{scenario}',
        output_folder = OUTPUT_FOLDER
    output:
        f'{OUTPUT_FOLDER}/Results/{{scenario}}_{{scope}}_{{constraint}}/{{scenario}}_{{scope}}_{{constraint}}.csv'
    notebook:
        'Mining power sizing -- Clean -- Bulk -- UpdatedJul2025.ipynb'
        
rule post_analysis:
    input:
        min_processing_values = "min_processing_values_dict_New.xlsx",
        scenario = f'{OUTPUT_FOLDER}/Results/{{scenario}}_{{scope}}_{{constraint}}/{{scenario}}_{{scope}}_{{constraint}}.csv'
    params:
        scope = '{scope}',
        output_path = f'{OUTPUT_FOLDER}/Final_Output_per_scenario'
    output:
        result = f'{OUTPUT_FOLDER}/Final_Output_per_scenario/{{scenario}}_{{scope}}_{{constraint}}.csv'
    notebook:
        'Post-analysis-UpdatedJul2025.ipynb'

rule post_post_analysis:
    input:
        files
    params:
        input_folder = rules.post_analysis.params.output_path,
        output_path = f'{OUTPUT_FOLDER}/Summaries'
    output:
        tech_scenario_comparison = f'{OUTPUT_FOLDER}/Summaries/tech_scenario_comparison.xlsx',
        all_scenario_comparison = f'{OUTPUT_FOLDER}/Summaries/all_scenarios_comparison_combined.xlsx'
    notebook:
        'Post Post Analysis-UpdatedJul2025.ipynb'