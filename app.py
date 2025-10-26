from shiny import App, render, ui, reactive
from fuel_analyst import fuel_analyst as fa
import os
import pandas as pd
import traceback
import shutil
import tempfile
import zipfile
from io import BytesIO
import copy

# Define the UI
app_ui = ui.page_fluid(
    ui.panel_title("Fuel Analyst Dashboard"),
    # Top-level tabs for different toolsets
    ui.navset_tab(
        # TAB 1: Fuel Analysis (existing functionality)
        ui.nav_panel(
            "Fuel Analysis",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.h4("Data Upload"),
                    ui.input_file("zip_upload", "Upload Input Data (ZIP)", accept=[".zip"], multiple=False),
                    ui.output_text_verbatim("zip_status"),
                    
                    ui.hr(),
                    ui.h4("⚙️ Analysis Parameters"),
                    
                    ui.input_select("fire_model", "Surface Fire Intensity Model:",
                                  choices=["Byram", "Other"], selected="Byram"),
                    
                    ui.input_checkbox("gen_fofem_tree", "Generate FOFEM Tree DataFrame", value=True),
                    ui.input_checkbox("gen_fofem_consume", "Generate FOFEM Consumption DataFrame", value=True),
                    
                    ui.hr(),
                    ui.accordion(
                        ui.accordion_panel(
                            "Advanced FOFEM Settings",
                            ui.input_select("region", "FOFEM Region:",
                                          choices=["InteriorWest", "PacificWest", "NorthEast", "SouthEast"],
                                          selected="InteriorWest"),
                            ui.input_select("season", "Season:",
                                          choices=["Spring", "Summer", "Fall", "Winter"],
                                          selected="Summer"),
                            ui.input_select("moisture_regime", "Moisture Regime:",
                                          choices=["Wet", "Moderate", "Dry", "Very Dry"],
                                          selected="Very Dry"),
                            ui.input_checkbox("soil_heating", "Use Soil Heating", value=False),
                        ),
                        ui.accordion_panel(
                            "Stand Summary Settings",
                            ui.h5("DBH Thresholds"),
                            ui.input_numeric("dbh_threshold_small", "Small DBH Threshold (cm):", value=5, min=0, max=100),
                            ui.input_numeric("dbh_threshold_medium", "Medium DBH Threshold (cm):", value=7.5, min=0, max=100),
                            ui.input_numeric("dbh_threshold_large", "Large DBH Threshold (cm):", value=12.5, min=0, max=100),
                            ui.p("These thresholds are used for density and basal area classes.", style="font-size: 0.85em; color: #666;"),
                            
                            ui.hr(),
                            ui.h5("Summary Categories (select which to include)"),
                            ui.input_checkbox_group(
                                "stand_summary_categories",
                                "",
                                choices={
                                    "total": "Total",
                                    "live": "Live",
                                    "dead": "Dead",
                                    "conifer": "Conifer",
                                    "broadleaf": "Broadleaf"
                                },
                                selected=["total", "live", "dead", "conifer", "broadleaf"]
                            ),
                            
                            ui.hr(),
                            ui.h5("Height Metrics"),
                            ui.input_checkbox_group(
                                "height_metrics",
                                "",
                                choices={"max": "Maximum", "mean": "Mean"},
                                selected=["max", "mean"]
                            ),
                            
                            ui.hr(),
                            ui.h5("Crown & Fire Metrics"),
                            ui.input_checkbox_group(
                                "crown_fire_metrics",
                                "",
                                choices={"min": "Minimum", "max": "Maximum", "mean": "Mean"},
                                selected=["min", "max", "mean"]
                            ),
                            
                            ui.hr(),
                            ui.h5("Canopy Fuel Load (CFL) Metrics"),
                            ui.input_checkbox_group(
                                "cfl_metrics",
                                "",
                                choices={"min": "Minimum", "max": "Maximum", "mean": "Mean", "sum": "Sum"},
                                selected=["min", "max", "mean", "sum"]
                            ),
                        ),
                        ui.accordion_panel(
                            "Woody Debris Settings",
                            ui.h5("Classification Systems"),
                            ui.input_checkbox("woody_canadian", "Canadian Classification", value=True),
                            ui.input_checkbox("woody_us", "U.S. Classification", value=True),
                            ui.input_checkbox("woody_modified", "Modified Classification", value=True),
                            ui.hr(),
                            ui.input_checkbox("woody_qmd_comparison", "Compare Measured vs Tallied QMD", value=True),
                        ),
                        ui.accordion_panel(
                            "Validation & Debug",
                            ui.input_checkbox("validate_folders", "Validate Input Folders Before Run", value=True),
                            ui.input_checkbox("show_debug", "Show Debug Information", value=False),
                        ),
                        open=False,
                        multiple=True,
                    ),
                    
                    ui.hr(),
                    ui.input_action_button("run_analysis", "Run Analysis", class_="btn-primary"),
                    ui.input_action_button("clear_output", "Clear Results", class_="btn-secondary"),
                    width=350
                ),
                
                ui.navset_tab(
                    ui.nav_panel(
                        "Data Setup",
                        ui.h2("📦 Input Data Preparation"),
                        ui.accordion(
                            ui.accordion_panel(
                                "📖 How to Prepare Your ZIP File",
                                ui.markdown("""
                                **Create a ZIP file with the following structure:**
                                
                                ```
                                your_data.zip
                                ├── 1_Plot_Attributes/
                                │   └── survey_0.csv          [REQUIRED]
                                ├── 2_Plants_Regeneration/
                                │   ├── survey_0.csv          [Optional]
                                │   └── regeneration_1.csv    [Optional]
                                ├── 3_Trees/
                                │   ├── survey_0.csv          [Optional]
                                │   ├── sapling_1.csv         [Optional]
                                │   └── tree_plot_2.csv       [Optional]
                                ├── 4_Canopy_Cover/
                                │   ├── survey_0.csv          [Optional]
                                │   └── transect_1.csv        [Optional]
                                └── 5_Woody_Debris/
                                    └── survey_0.csv          [Optional]
                                ```
                                
                                **Required Columns in 1_Plot_Attributes/survey_0.csv:**
                                - `_date`, `treatment_area`, `treatment_unit`, `treatment_type`, `plot_id`, `form_select`
                                
                                **Note:** The `form_select` column determines which other forms are processed.
                                
                                **To create the ZIP:**
                                1. Create a folder with subfolders as shown above
                                2. Place your CSV files in the appropriate subfolders
                                3. Right-click the main folder and select "Send to > Compressed (zipped) folder" (Windows)
                                   or "Compress" (macOS)
                                """),
                            ),
                            open=True
                        ),
                        ui.hr(),
                        ui.h3("📂 Uploaded Data Structure"),
                        ui.output_text_verbatim("folder_structure"),
                        ui.hr(),
                        ui.h3("Preview: survey_0.csv (Plot Attributes)"),
                        ui.output_text("plot_csv_status"),
                        ui.output_data_frame("plot_csv_preview"),
                    ),
                    ui.nav_panel(
                        "Analysis Status",
                        ui.h2("Fuel Analysis Status"),
                        ui.output_text_verbatim("status"),
                        ui.output_text_verbatim("debug_info"),
                    ),
                    ui.nav_panel(
                        "Results Summary",
                        ui.h2("Analysis Results"),
                        ui.output_text_verbatim("results"),
                        ui.hr(),
                        ui.h3("📥 Download Results"),
                        ui.download_button("download_all", "Download All Results (ZIP)", class_="btn-success"),
                        ui.p("Or download individual files:"),
                        ui.download_button("download_master_fuel", "Master Fuel DataFrame"),
                        ui.download_button("download_master_tree", "Master Tree DataFrame"),
                        ui.download_button("download_fofem_tree", "FOFEM Tree DataFrame"),
                        ui.download_button("download_fofem_consume", "FOFEM Consume DataFrame"),
                        ui.hr(),
                        ui.h3("Generated Files"),
                        ui.output_text_verbatim("output_files"),
                    ),
                    ui.nav_panel(
                        "Data Preview",
                        ui.h2("Master Fuel DataFrame Preview"),
                        ui.output_text("preview_status"),
                        ui.output_data_frame("master_df_preview"),
                        ui.hr(),
                        ui.h3("Master Tree DataFrame Preview"),
                        ui.output_data_frame("tree_df_preview"),
                    ),
                )
            )
        ),
        
        # TAB 2: Second Toolset (placeholder)
        ui.nav_panel(
            "🔧 Tool 2",
            ui.layout_sidebar(
                ui.sidebar(
                    ui.h4("⚙️ Tool 2 Settings"),
                    ui.p("Settings and controls will go here."),
                    ui.hr(),
                    ui.input_action_button("tool2_run", "Run Tool 2", class_="btn-primary"),
                    width=350
                ),
                ui.div(
                    ui.h2("Tool 2 - Coming Soon"),
                    ui.p("This is a placeholder for the second toolset."),
                    ui.p("Functionality will be added later."),
                )
            )
        ),
    )
)

# Define the server logic
def server(input, output, session):
    
    # Reactive values to store analysis status and data
    analysis_status = reactive.Value("")
    analysis_results = reactive.Value("")
    debug_info_text = reactive.Value("")
    zip_upload_status = reactive.Value("")
    
    # Create a session-specific output directory
    session_id = session.ns  # Get unique session identifier
    session_output_dir = os.path.join(tempfile.gettempdir(), f"fuel_analyst_{session_id}")
    os.makedirs(session_output_dir, exist_ok=True)
    
    # Reactive values for file paths (work with uploaded ZIP or local folders)
    input_folder = reactive.Value(None)
    output_folder = reactive.Value(session_output_dir)
    
    # Cleanup handler - remove temp directories when session ends
    @reactive.Effect
    def _():
        session.on_ended(lambda: cleanup_session_files())
    
    def cleanup_session_files():
        """Clean up temporary files when session ends"""
        try:
            # Clean up input folder if it exists
            in_folder = input_folder.get()
            if in_folder and os.path.exists(in_folder):
                shutil.rmtree(in_folder, ignore_errors=True)
            
            # Clean up output folder if it exists
            out_folder = output_folder.get()
            if out_folder and os.path.exists(out_folder):
                shutil.rmtree(out_folder, ignore_errors=True)
        except Exception:
            pass  # Ignore cleanup errors
    
    def validate_input_structure(in_folder):
        """Validate that input folder has required structure"""
        validation_results = []
        expected_folders = {
            '1_Plot_Attributes': 'survey_0.csv',
            '2_Plants_Regeneration': None,
            '3_Trees': None,
            '4_Canopy_Cover': None,
            '5_Woody_Debris': None
        }
        
        for folder, required_file in expected_folders.items():
            folder_path = os.path.join(in_folder, folder)
            if os.path.exists(folder_path):
                if required_file:
                    file_path = os.path.join(folder_path, required_file)
                    if os.path.exists(file_path):
                        validation_results.append(f"✓ {folder}/{required_file}")
                    else:
                        validation_results.append(f"✗ {folder} missing {required_file}")
                else:
                    validation_results.append(f"✓ {folder} exists")
            else:
                validation_results.append(f"✗ {folder} not found")
        
        return "\n".join(validation_results)
    
    @reactive.Effect
    @reactive.event(input.zip_upload)
    def handle_zip_upload():
        """Handle ZIP file upload and extraction"""
        try:
            file_info = input.zip_upload()
            
            if file_info is None or len(file_info) == 0:
                zip_upload_status.set("⚠️ No file uploaded")
                return
            
            # Create temporary directory for extraction
            temp_extract_dir = tempfile.mkdtemp(prefix="fuel_analyst_extract_")
            
            # Extract ZIP file
            zip_path = file_info[0]["datapath"]
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            
            # Handle potential nested folder structure
            # Check if extraction created a single root folder
            extracted_items = os.listdir(temp_extract_dir)
            
            if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, extracted_items[0])):
                # Single folder was extracted - use it as the root
                actual_data_folder = os.path.join(temp_extract_dir, extracted_items[0])
            else:
                # Multiple items or files at root - use extract dir as is
                actual_data_folder = temp_extract_dir
            
            # Verify expected folders exist
            expected_folders = ['1_Plot_Attributes', '2_Plants_Regeneration', '3_Trees', 
                              '4_Canopy_Cover', '5_Woody_Debris']
            found_folders = [f for f in expected_folders if os.path.exists(os.path.join(actual_data_folder, f))]
            
            # Set the input folder to the correct location
            input_folder.set(actual_data_folder)
            
            # Count extracted files
            total_files = sum([len(files) for _, _, files in os.walk(actual_data_folder)])
            
            zip_upload_status.set(
                f"✅ ZIP uploaded and extracted!\n"
                f"📂 {total_files} files extracted\n"
                f"📁 Found {len(found_folders)} data folders: {', '.join(found_folders)}\n"
                f"🗂️ Location: {os.path.basename(actual_data_folder)}"
            )
            
        except zipfile.BadZipFile:
            zip_upload_status.set("❌ Error: Invalid ZIP file")
        except Exception as e:
            zip_upload_status.set(f"❌ Upload error: {str(e)}\n{traceback.format_exc()}")
    
    @output
    @render.text
    def zip_status():
        return zip_upload_status.get()
    
    @reactive.Effect
    @reactive.event(input.clear_output)
    def clear_results():
        """Clear all result displays"""
        analysis_status.set("")
        analysis_results.set("")
        debug_info_text.set("")
    
    @reactive.Effect
    @reactive.event(input.run_analysis)
    def run_fuel_analysis():
        """Run the fuel analyst when button is clicked"""
        try:
            analysis_status.set("🔄 Initializing analysis...")
            debug_info_text.set("")
            
            # Get input and output folders
            in_folder = input_folder.get()
            out_folder = output_folder.get()
            
            # Validate input folder exists
            if in_folder is None:
                analysis_status.set("❌ Error: Please upload a ZIP file with input data first!")
                return
            
            if not os.path.exists(in_folder):
                analysis_status.set(f"❌ Error: Input folder does not exist:\n{in_folder}")
                return
            
            # Get input parameters from UI
            surface_model = input.fire_model()
            gen_tree = input.gen_fofem_tree()
            gen_consume = input.gen_fofem_consume()
            
            # Validate folder structure if requested
            if input.validate_folders():
                analysis_status.set("🔍 Validating input folder structure...")
                validation_msg = validate_input_structure(in_folder)
                debug_info_text.set(f"Folder Structure Validation:\n{validation_msg}")
                
                if "✗" in validation_msg:
                    analysis_status.set("⚠️ Warning: Some expected folders/files are missing.\nProceeding with analysis...")
            
            # Build custom parameter dictionaries based on user inputs
            analysis_status.set("⚙️ Configuring analysis parameters...")
            
            # Get user selections
            dbh_small = input.dbh_threshold_small()
            dbh_medium = input.dbh_threshold_medium()
            dbh_large = input.dbh_threshold_large()
            summary_cats = list(input.stand_summary_categories())
            height_metrics = list(input.height_metrics())
            crown_fire_metrics = list(input.crown_fire_metrics())
            cfl_metrics = list(input.cfl_metrics())
            
            # Stand summary parameters
            stand_params = copy.deepcopy(fa.default_stand_summary_dict)
            
            # Update summary categories for applicable attributes
            for attr in ['dens', 'ba', 'ht', 'dcbh', 'fsg', 'branches', 'wood', 'bark']:
                if attr in stand_params:
                    # Filter to only include categories that make sense for this attribute
                    available = stand_params[attr]['summary']
                    stand_params[attr]['summary'] = [c for c in summary_cats if c in available]
            
            # Update CBH summary (doesn't include 'dead')
            if 'cbh' in stand_params:
                cbh_cats = [c for c in summary_cats if c in ['total', 'live', 'conifer', 'broadleaf']]
                stand_params['cbh']['summary'] = cbh_cats
            
            # Update CFL summary (only live trees)
            if 'cfl' in stand_params:
                cfl_cats = [c for c in summary_cats if c in ['total', 'conifer', 'broadleaf']]
                stand_params['cfl']['summary'] = cfl_cats
                stand_params['cfl']['metrics'] = cfl_metrics
            
            # Update foliage summary (only live trees)  
            if 'foliage' in stand_params:
                foliage_cats = [c for c in summary_cats if c in ['total', 'conifer', 'broadleaf']]
                stand_params['foliage']['summary'] = foliage_cats
            
            # Update metrics
            if 'ht' in stand_params:
                stand_params['ht']['metrics'] = height_metrics
            for attr in ['cbh', 'dcbh', 'fsg', 'flame_length', 'fire_intensity']:
                if attr in stand_params:
                    stand_params[attr]['metrics'] = crown_fire_metrics
            
            # Update DBH thresholds
            stand_params['dens']['classes']['dbh'] = [0, dbh_small, dbh_medium, dbh_large]
            stand_params['ba']['classes']['dbh'] = [0, dbh_small, dbh_medium, dbh_large]
            stand_params['ht']['classes']['dbh'] = [0, dbh_small]
            stand_params['cbh']['classes']['dbh'] = [0, dbh_small]
            stand_params['dcbh']['classes']['dbh'] = [0, dbh_small]
            stand_params['fsg']['classes']['dbh'] = [0, dbh_small]
            stand_params['cfl']['classes']['dbh'] = [0, dbh_small]
            stand_params['cbd']['classes']['dbh'] = [0, dbh_small]
            
            # Woody debris parameters
            woody_params = copy.deepcopy(fa.default_woody_debris_dict)
            
            # Update which classification systems to process
            woody_params['woody_debris_classes']['canadian']['process_classes'] = input.woody_canadian()
            woody_params['woody_debris_classes']['us']['process_classes'] = input.woody_us()
            woody_params['woody_debris_classes']['modified']['process_classes'] = input.woody_modified()
            woody_params['measure_vs_tally_qmd_comparison'] = input.woody_qmd_comparison()
            
            # FOFEM consume parameters
            fofem_params = copy.deepcopy(fa.default_fofem_consume_dict)
            fofem_params['region'] = input.region()
            fofem_params['season'] = input.season()
            fofem_params['moisture_regime'] = input.moisture_regime()
            fofem_params['soil_heating']['use_soil_heating'] = input.soil_heating()
            
            if input.show_debug():
                debug_text = f"Configuration:\n"
                debug_text += f"  Surface Fire Model: {surface_model}\n"
                debug_text += f"  DBH Thresholds: {dbh_small}, {dbh_medium}, {dbh_large} cm\n"
                debug_text += f"  Summary Categories: {', '.join(summary_cats)}\n"
                debug_text += f"  Height Metrics: {', '.join(height_metrics)}\n"
                debug_text += f"  Crown/Fire Metrics: {', '.join(crown_fire_metrics)}\n"
                debug_text += f"  CFL Metrics: {', '.join(cfl_metrics)}\n"
                debug_text += f"  Woody Debris - Canadian: {input.woody_canadian()}\n"
                debug_text += f"  Woody Debris - U.S.: {input.woody_us()}\n"
                debug_text += f"  Woody Debris - Modified: {input.woody_modified()}\n"
                debug_text += f"  Woody QMD Comparison: {input.woody_qmd_comparison()}\n"
                debug_text += f"  FOFEM Region: {input.region()}\n"
                debug_text += f"  Season: {input.season()}\n"
                debug_text += f"  Moisture Regime: {input.moisture_regime()}\n"
                debug_text += f"  Soil Heating: {input.soil_heating()}\n"
                debug_text += f"  Generate FOFEM Tree DF: {gen_tree}\n"
                debug_text += f"  Generate FOFEM Consume DF: {gen_consume}\n"
                debug_info_text.set(debug_text)
            
            # Run the fuel analyst function
            analysis_status.set("🔥 Running fuel analysis...\n(This may take several minutes)")
            
            fa.fuel_analyst(
                in_folder=in_folder,
                out_folder=out_folder,
                surface_fire_intensity_model=surface_model,
                stand_summary_params=stand_params,
                woody_debris_params=woody_params,
                fofem_consume_params=fofem_params,
                gen_fofem_tree_df=gen_tree,
                gen_fofem_consume_df=gen_consume
            )
            
            analysis_status.set("✅ Analysis completed successfully!")
            
            # List output files
            if os.path.exists(out_folder):
                files = os.listdir(out_folder)
                csv_files = [f for f in files if f.endswith('.csv')]
                
                # Get file sizes
                file_info = []
                for csv_file in csv_files:
                    file_path = os.path.join(out_folder, csv_file)
                    size_bytes = os.path.getsize(file_path)
                    size_kb = size_bytes / 1024
                    file_info.append(f"  {csv_file} ({size_kb:.1f} KB)")
                
                results_text = f"Generated {len(csv_files)} CSV file(s):\n" + "\n".join(file_info)
                analysis_results.set(results_text)
            
        except Exception as e:
            error_trace = traceback.format_exc()
            analysis_status.set(f"❌ Error during analysis:\n{str(e)}")
            if input.show_debug():
                debug_info_text.set(f"Full Error Traceback:\n{error_trace}")
            analysis_results.set("")
    
    @output
    @render.text
    def status():
        return analysis_status.get()
    
    @output
    @render.text
    def results():
        return analysis_results.get()
    
    @output
    @render.text
    def debug_info():
        if input.show_debug():
            return debug_info_text.get()
        return ""
    
    @output
    @render.text
    def output_files():
        out_folder = output_folder.get()
        if os.path.exists(out_folder):
            all_files = []
            for root, dirs, files in os.walk(out_folder):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), out_folder)
                    all_files.append(rel_path)
            return f"Output folder contents:\n" + "\n".join(all_files) if all_files else "No files yet"
        return "Output folder does not exist yet"
    
    @output
    @render.text
    def preview_status():
        out_folder = output_folder.get()
        master_df_path = os.path.join(out_folder, 'master_fuel_df.csv')
        
        if os.path.exists(master_df_path):
            return "✓ Data loaded (showing first 100 rows)"
        return "⚠️ No data available. Run analysis first."
    
    @output
    @render.data_frame
    def master_df_preview():
        out_folder = output_folder.get()
        master_df_path = os.path.join(out_folder, 'master_fuel_df.csv')
        
        if os.path.exists(master_df_path):
            try:
                df = pd.read_csv(master_df_path)
                # Return first 100 rows
                return render.DataGrid(df.head(100), width="100%", height="400px")
            except Exception as e:
                return render.DataGrid(pd.DataFrame({'Error': [str(e)]}))
        
        return render.DataGrid(pd.DataFrame({'Message': ['No data available']}))
    
    @output
    @render.data_frame
    def tree_df_preview():
        out_folder = output_folder.get()
        tree_df_path = os.path.join(out_folder, 'master_tree_df.csv')
        
        if os.path.exists(tree_df_path):
            try:
                df = pd.read_csv(tree_df_path)
                # Return first 100 rows
                return render.DataGrid(df.head(100), width="100%", height="400px")
            except Exception as e:
                return render.DataGrid(pd.DataFrame({'Error': [str(e)]}))
        
        return render.DataGrid(pd.DataFrame({'Message': ['No data available']}))
    
    # ===== DATA VALIDATION FUNCTIONS =====
    
    def scan_folder_structure(in_folder):
        """Scan and report the structure of input folders"""
        if not os.path.exists(in_folder):
            return f"❌ Input folder does not exist: {in_folder}"
        
        folder_info = {
            '1_Plot_Attributes': ['survey_0.csv'],
            '2_Plants_Regeneration': ['survey_0.csv', 'regeneration_1.csv'],
            '3_Trees': ['survey_0.csv', 'sapling_1.csv', 'tree_plot_2.csv'],
            '4_Canopy_Cover': ['survey_0.csv', 'transect_1.csv'],
            '5_Woody_Debris': ['survey_0.csv']
        }
        
        structure_report = []
        structure_report.append(f"Input Folder: {in_folder}\n")
        structure_report.append("=" * 60)
        
        for folder_name, expected_files in folder_info.items():
            folder_path = os.path.join(in_folder, folder_name)
            structure_report.append(f"\n📁 {folder_name}")
            
            if os.path.exists(folder_path):
                actual_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
                
                # Check expected files
                for expected_file in expected_files:
                    if expected_file in actual_files:
                        file_path = os.path.join(folder_path, expected_file)
                        file_size = os.path.getsize(file_path) / 1024  # KB
                        
                        # Try to get row count
                        try:
                            df = pd.read_csv(file_path)
                            row_count = len(df)
                            col_count = len(df.columns)
                            structure_report.append(
                                f"  ✓ {expected_file} ({file_size:.1f} KB, {row_count} rows, {col_count} cols)"
                            )
                        except Exception as e:
                            structure_report.append(
                                f"  ⚠ {expected_file} ({file_size:.1f} KB, Error reading: {str(e)[:30]})"
                            )
                    else:
                        structure_report.append(f"  ✗ {expected_file} (MISSING)")
                
                # Show additional files not in expected list
                extra_files = [f for f in actual_files if f not in expected_files]
                for extra_file in extra_files:
                    file_path = os.path.join(folder_path, extra_file)
                    file_size = os.path.getsize(file_path) / 1024
                    structure_report.append(f"  + {extra_file} ({file_size:.1f} KB)")
            else:
                structure_report.append(f"  ✗ Folder does not exist")
        
        return "\n".join(structure_report)
    
    @output
    @render.text
    def folder_structure():
        # Get current input folder
        in_folder = input_folder.get()
        if in_folder is None:
            return "⚠️ No data uploaded yet. Please upload a ZIP file containing your survey data."
        return scan_folder_structure(in_folder)
    
    @output
    @render.text
    def plot_csv_status():
        in_folder = input_folder.get()
        if in_folder is None:
            return "⚠️ No data uploaded yet"
        
        plot_csv_path = os.path.join(in_folder, '1_Plot_Attributes', 'survey_0.csv')
        
        if os.path.exists(plot_csv_path):
            try:
                df = pd.read_csv(plot_csv_path)
                
                # Check for required columns
                required_cols = ['_date', 'treatment_area', 'treatment_unit', 
                               'treatment_type', 'plot_id', 'form_select']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    return f"⚠️ Warning: Missing required columns: {', '.join(missing_cols)}"
                else:
                    return f"✓ Valid plot attributes CSV ({len(df)} plots, {len(df.columns)} columns)"
            except Exception as e:
                return f"❌ Error reading CSV: {str(e)}"
        
        return "⚠️ survey_0.csv not found in 1_Plot_Attributes folder"
    
    @output
    @render.data_frame
    def plot_csv_preview():
        in_folder = input_folder.get()
        
        if in_folder is None:
            return render.DataGrid(pd.DataFrame({
                'Message': ['No data available. Upload a ZIP file with your survey data.']
            }))
        
        plot_csv_path = os.path.join(in_folder, '1_Plot_Attributes', 'survey_0.csv')
        
        if os.path.exists(plot_csv_path):
            try:
                df = pd.read_csv(plot_csv_path)
                # Show first 50 rows
                return render.DataGrid(df.head(50), width="100%", height="400px")
            except Exception as e:
                return render.DataGrid(pd.DataFrame({'Error': [str(e)]}))
        
        return render.DataGrid(pd.DataFrame({
            'Message': ['No data available. Upload a ZIP file containing 1_Plot_Attributes/survey_0.csv']
        }))
    
    # ===== DOWNLOAD HANDLERS =====
    
    @render.download(filename="fuel_analyst_results.zip")
    def download_all():
        """Create and download a ZIP file of all results"""
        out_folder = output_folder.get()
        
        # Ensure output folder exists
        if not out_folder or not os.path.exists(out_folder):
            raise FileNotFoundError(f"Output folder does not exist: {out_folder}")
        
        # Create ZIP in memory
        zip_buffer = BytesIO()
        files_added = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Walk through output folder and add all files
            for root, dirs, files in os.walk(out_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        try:
                            arcname = os.path.relpath(file_path, out_folder)
                            zip_file.write(file_path, arcname)
                            files_added += 1
                        except (OSError, IOError) as e:
                            # Skip files that can't be read, but continue with others
                            continue
            
            # Check if any files were added before closing the zip
            if files_added == 0:
                raise FileNotFoundError("No files found to download. Please run analysis first.")
        
        # Use yield like in the sample app
        zip_buffer.seek(0)
        yield zip_buffer.getvalue()
    
    @render.download(filename="master_fuel_df.csv")
    def download_master_fuel():
        """Download master fuel DataFrame"""
        out_folder = output_folder.get()
        file_path = os.path.join(out_folder, 'master_fuel_df.csv')
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: master_fuel_df.csv. Please run analysis first.")
        
        with open(file_path, 'rb') as f:
            yield f.read()
    
    @render.download(filename="master_tree_df.csv")
    def download_master_tree():
        """Download master tree DataFrame"""
        out_folder = output_folder.get()
        file_path = os.path.join(out_folder, 'master_tree_df.csv')
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: master_tree_df.csv. Please run analysis first.")
        
        with open(file_path, 'rb') as f:
            yield f.read()
    
    @render.download(filename="fofem_tree_df.csv")
    def download_fofem_tree():
        """Download FOFEM tree DataFrame"""
        out_folder = output_folder.get()
        file_path = os.path.join(out_folder, 'fofem_tree_df.csv')
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: fofem_tree_df.csv. Please run analysis first.")
        
        with open(file_path, 'rb') as f:
            yield f.read()
    
    @render.download(filename="fofem_consume_df.csv")
    def download_fofem_consume():
        """Download FOFEM consumption DataFrame"""
        out_folder = output_folder.get()
        file_path = os.path.join(out_folder, 'fofem_consume_df.csv')
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: fofem_consume_df.csv. Please run analysis first.")
        
        with open(file_path, 'rb') as f:
            yield f.read()
    
    # ===== TOOL 2 PLACEHOLDER FUNCTIONS =====
    
    @reactive.Effect
    @reactive.event(input.tool2_run)
    def run_tool2():
        """Placeholder function for Tool 2"""
        # TODO: Implement Tool 2 functionality
        pass

# Create the Shiny app
app = App(app_ui, server)