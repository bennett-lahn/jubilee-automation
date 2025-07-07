import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.checkbox import CheckBox
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import ObjectProperty, StringProperty, NumericProperty, BooleanProperty
from kivy.lang import Builder
import threading
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass

# Import Jubilee components
from science_jubilee.Machine import Machine
from Trickler import Trickler
from Scale import Scale
from trickler_labware import WeightWell, WeightWellSet

# Configure Kivy for touch interface
Window.softinput_mode = 'below_target'
kivy.require('2.0.0')

# KV Language string for custom styling
KV = '''
#:import utils kivy.utils

<CustomButton@Button>:
    background_color: utils.get_color_from_hex('#2196F3')
    background_normal: ''
    color: 1, 1, 1, 1
    size_hint_y: None
    height: dp(60)
    font_size: dp(18)
    canvas.before:
        Color:
            rgba: utils.get_color_from_hex('#1976D2') if self.state == 'down' else utils.get_color_from_hex('#2196F3')
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<CustomLabel@Label>:
    color: utils.get_color_from_hex('#212121')
    font_size: dp(16)
    size_hint_y: None
    height: dp(40)

<WeightWellButton@Button>:
    background_color: utils.get_color_from_hex('#4CAF50') if self.selected else utils.get_color_from_hex('#E0E0E0')
    background_normal: ''
    color: 1, 1, 1, 1 if self.selected else 0, 0, 0, 1
    size_hint: None, None
    size: dp(80), dp(80)
    font_size: dp(12)
    canvas.before:
        Color:
            rgba: self.background_color
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]

<MainScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        # Header
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            CustomLabel:
                text: 'Jubilee Powder Dispensing System'
                font_size: dp(24)
                bold: True
                halign: 'center'
        
        # Platform visualization
        BoxLayout:
            orientation: 'horizontal'
            size_hint_y: 0.6
            
            # Left side - Scale
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.2
                padding: dp(10)
                
                CustomLabel:
                    text: 'Scale'
                    halign: 'center'
                    bold: True
                
                BoxLayout:
                    orientation: 'vertical'
                    canvas.before:
                        Color:
                            rgba: utils.get_color_from_hex('#FF9800')
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    CustomLabel:
                        text: 'Connected' if root.scale_connected else 'Disconnected'
                        halign: 'center'
                        color: 1, 1, 1, 1
                    
                    CustomLabel:
                        text: f'{root.current_weight:.3f}g'
                        halign: 'center'
                        color: 1, 1, 1, 1
                        font_size: dp(20)
                        bold: True
            
            # Center - Platform
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.6
                padding: dp(10)
                
                CustomLabel:
                    text: 'Jubilee Platform'
                    halign: 'center'
                    bold: True
                
                GridLayout:
                    cols: 3
                    spacing: dp(5)
                    padding: dp(10)
                    canvas.before:
                        Color:
                            rgba: utils.get_color_from_hex('#F5F5F5')
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(8)]
                    
                    WeightWellButton:
                        text: 'A1\\n0.0g'
                        well_id: 'A1'
                        selected: root.is_well_selected('A1')
                        on_press: root.toggle_well('A1')
                    
                    WeightWellButton:
                        text: 'A2\\n0.0g'
                        well_id: 'A2'
                        selected: root.is_well_selected('A2')
                        on_press: root.toggle_well('A2')
                    
                    WeightWellButton:
                        text: 'A3\\n0.0g'
                        well_id: 'A3'
                        selected: root.is_well_selected('A3')
                        on_press: root.toggle_well('A3')
                    
                    WeightWellButton:
                        text: 'B1\\n0.0g'
                        well_id: 'B1'
                        selected: root.is_well_selected('B1')
                        on_press: root.toggle_well('B1')
                    
                    WeightWellButton:
                        text: 'B2\\n0.0g'
                        well_id: 'B2'
                        selected: root.is_well_selected('B2')
                        on_press: root.toggle_well('B2')
                    
                    WeightWellButton:
                        text: 'B3\\n0.0g'
                        well_id: 'B3'
                        selected: root.is_well_selected('B3')
                        on_press: root.toggle_well('B3')
                    
                    WeightWellButton:
                        text: 'C1\\n0.0g'
                        well_id: 'C1'
                        selected: root.is_well_selected('C1')
                        on_press: root.toggle_well('C1')
                    
                    WeightWellButton:
                        text: 'C2\\n0.0g'
                        well_id: 'C2'
                        selected: root.is_well_selected('C2')
                        on_press: root.toggle_well('C2')
                    
                    WeightWellButton:
                        text: 'C3\\n0.0g'
                        well_id: 'C3'
                        selected: root.is_well_selected('C3')
                        on_press: root.toggle_well('C3')
            
            # Right side - Controls
            BoxLayout:
                orientation: 'vertical'
                size_hint_x: 0.2
                padding: dp(10)
                spacing: dp(10)
                
                CustomLabel:
                    text: 'Controls'
                    halign: 'center'
                    bold: True
                
                CustomButton:
                    text: 'Set Weights'
                    on_press: root.show_weight_dialog()
                
                CustomButton:
                    text: 'Start Job'
                    on_press: root.start_job()
                    disabled: not root.can_start_job()
                
                CustomButton:
                    text: 'Stop Job'
                    on_press: root.stop_job()
                    disabled: not root.job_running
        
        # Status bar
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            canvas.before:
                Color:
                    rgba: utils.get_color_from_hex('#E0E0E0')
                Rectangle:
                    pos: self.pos
                    size: self.size
            
            CustomLabel:
                text: root.status_text
                halign: 'left'
                valign: 'middle'
                text_size: self.size

<WeightDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Set Target Weights'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        ScrollView:
            GridLayout:
                cols: 2
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
                
                CustomLabel:
                    text: 'Well'
                    bold: True
                
                CustomLabel:
                    text: 'Target Weight (g)'
                    bold: True
                
                # Dynamic weight inputs will be added here
                id: weight_inputs
        
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(10)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.dismiss()
                background_color: utils.get_color_from_hex('#F44336')
            
            CustomButton:
                text: 'Apply'
                on_press: root.apply_weights()

<ChecklistDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Pre-Job Checklist'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        ScrollView:
            GridLayout:
                cols: 2
                spacing: dp(10)
                size_hint_y: None
                height: self.minimum_height
                
                CustomLabel:
                    text: 'Check Item'
                    bold: True
                
                CustomLabel:
                    text: 'Status'
                    bold: True
                
                # Dynamic checklist items will be added here
                id: checklist_items
        
        BoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(10)
            
            CustomButton:
                text: 'Cancel'
                on_press: root.dismiss()
                background_color: utils.get_color_from_hex('#F44336')
            
            CustomButton:
                text: 'Start Job'
                on_press: root.start_job()
                disabled: not root.all_checked()

<ProgressDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Job Progress'
            font_size: dp(20)
            bold: True
            halign: 'center'
        
        CustomLabel:
            text: f'Completed: {root.completed_wells}/{root.total_wells}'
            halign: 'center'
            font_size: dp(18)
        
        ProgressBar:
            value: root.progress_value
            max: 100
            size_hint_y: None
            height: dp(30)
        
        CustomLabel:
            text: root.current_well_text
            halign: 'center'
        
        CustomButton:
            text: 'Stop Job'
            on_press: root.stop_job()
            background_color: utils.get_color_from_hex('#F44336')

<FinishedDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Job Completed!'
            font_size: dp(24)
            bold: True
            halign: 'center'
            color: utils.get_color_from_hex('#4CAF50')
        
        CustomLabel:
            text: 'All wells have been filled successfully.'
            halign: 'center'
        
        CustomButton:
            text: 'OK'
            on_press: root.dismiss()
            background_color: utils.get_color_from_hex('#4CAF50')

<ErrorDialog>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        
        CustomLabel:
            text: 'Error'
            font_size: dp(20)
            bold: True
            halign: 'center'
            color: utils.get_color_from_hex('#F44336')
        
        ScrollView:
            CustomLabel:
                text: root.error_message
                halign: 'center'
                text_size: self.size
        
        CustomButton:
            text: 'OK'
            on_press: root.dismiss()
            background_color: utils.get_color_from_hex('#F44336')
'''

Builder.load_string(KV)

@dataclass
class JobWell:
    """Represents a well in a dispensing job"""
    well_id: str
    target_weight: float
    current_weight: float = 0.0
    completed: bool = False

class JubileeManager:
    """Manages the Jubilee machine and related components"""
    
    def __init__(self):
        self.machine: Optional[Machine] = None
        self.trickler: Optional[Trickler] = None
        self.connected = False
        self._last_weight = 0.0
        self._weight_update_callback = None
        
    def connect(self, machine_address: str = "192.168.1.2", scale_port: str = "/dev/ttyUSB0"):
        """Connect to Jubilee machine and initialize trickler with scale"""
        try:
            # Load configuration
            config = self._load_config()
            
            # Connect to machine
            self.machine = Machine(address=machine_address)
            self.machine.connect()
            
            # Initialize scale (will be passed to trickler)
            scale = Scale(port=scale_port)
            scale.connect()
            
            # Initialize trickler with the scale
            trickler_config = config.get("trickler", {})
            self.trickler = Trickler(
                index=trickler_config.get("tool_index", 0),
                name=trickler_config.get("tool_name", "trickler"),
                config=trickler_config.get("config_file", "trickler_config"),
                scale=scale
            )
            
            # Set up weight update callback
            self._setup_weight_monitoring()
            
            self.connected = True
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        try:
            with open("jubilee_config.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("Configuration file not found, using defaults")
            return {}
        except json.JSONDecodeError as e:
            print(f"Configuration file error: {e}")
            return {}
    
    def disconnect(self):
        """Disconnect from all components"""
        if self.machine:
            self.machine.disconnect()
        if self.trickler and self.trickler.scale:
            self.trickler.scale.disconnect()
        self.connected = False
    
    def _setup_weight_monitoring(self):
        """Set up weight monitoring through the trickler's scale"""
        if self.trickler and self.trickler.scale:
            # Store reference to scale for monitoring
            self._scale = self.trickler.scale
    
    def get_current_weight(self) -> float:
        """Get current weight from trickler's scale"""
        if self.trickler and self.trickler.scale and self.trickler.scale.is_connected:
            try:
                weight = self.trickler.scale.get_weight()
                self._last_weight = weight
                return weight
            except Exception as e:
                print(f"Weight reading error: {e}")
                return self._last_weight
        return self._last_weight
    
    def set_weight_update_callback(self, callback):
        """Set callback for weight updates"""
        self._weight_update_callback = callback
    
    def update_weight_from_trickler(self, weight: float):
        """Update weight when trickler retrieves new weight"""
        self._last_weight = weight
        if self._weight_update_callback:
            self._weight_update_callback(weight)
    
    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """Dispense powder to a specific well using the trickler"""
        if not self.connected or not self.trickler:
            return False
        
        try:
            # Create a WeightWell object for the target location
            # Note: You'll need to define the actual coordinates for each well
            well_coordinates = self._get_well_coordinates(well_id)
            target_well = WeightWell(
                name=well_id,
                x=well_coordinates[0],
                y=well_coordinates[1],
                z=well_coordinates[2],
                target_weight=target_weight
            )
            
            # Use the trickler to dispense to the well
            # The trickler will handle scale monitoring internally
            self.trickler.dispense_to_well(target_well, target_weight)
            
            # Update weight display when trickler gets new weight
            if self.trickler.scale:
                current_weight = self.trickler.scale.get_weight()
                self.update_weight_from_trickler(current_weight)
            
            return True
            
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False
    
    def _get_well_coordinates(self, well_id: str) -> tuple:
        """Get coordinates for a specific well"""
        # Load well coordinates from configuration
        config = self._load_config()
        ui_config = config.get("ui", {})
        well_layout = ui_config.get("well_layout", {})
        
        # Default well coordinates (you'll need to adjust these based on your setup)
        default_positions = {
            'A1': (50, 50, 0),   'A2': (150, 50, 0),   'A3': (250, 50, 0),
            'B1': (50, 150, 0),  'B2': (150, 150, 0),  'B3': (250, 150, 0),
            'C1': (50, 250, 0),  'C2': (150, 250, 0),  'C3': (250, 250, 0)
        }
        
        # Use custom positions if defined in config
        custom_positions = well_layout.get("well_positions", {})
        well_positions = {**default_positions, **custom_positions}
        
        return well_positions.get(well_id, (0, 0, 0))

class MainScreen(Screen):
    """Main screen of the Jubilee GUI application"""
    
    # Properties
    status_text = StringProperty("Ready")
    current_weight = NumericProperty(0.0)
    scale_connected = BooleanProperty(False)
    job_running = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jubilee_manager = JubileeManager()
        self.selected_wells = set()
        self.well_weights = {}  # well_id -> target_weight
        self.job_wells = []
        self.current_job_thread = None
        
        # Set up weight update callback
        self.jubilee_manager.set_weight_update_callback(self._on_weight_update)
        
        # Start weight monitoring (will use trickler's scale)
        Clock.schedule_interval(self.update_weight, 0.5)
        
        # Try to connect
        self.connect_to_system()
    
    def connect_to_system(self):
        """Connect to Jubilee system"""
        self.status_text = "Connecting..."
        threading.Thread(target=self._connect_thread, daemon=True).start()
    
    def _connect_thread(self):
        """Connection thread to avoid blocking UI"""
        success = self.jubilee_manager.connect()
        if success:
            self.status_text = "Connected"
            # Check if trickler and scale are available
            if self.jubilee_manager.trickler and self.jubilee_manager.trickler.scale:
                self.scale_connected = True
            else:
                self.scale_connected = False
        else:
            self.status_text = "Connection failed"
            self.scale_connected = False
    
    def update_weight(self, dt):
        """Update current weight display"""
        if self.jubilee_manager.connected:
            self.current_weight = self.jubilee_manager.get_current_weight()
    
    def _on_weight_update(self, weight: float):
        """Callback for weight updates from trickler"""
        # Update the UI with new weight (called from main thread)
        Clock.schedule_once(lambda dt: setattr(self, 'current_weight', weight), 0)
    
    def toggle_well(self, well_id: str):
        """Toggle selection of a well"""
        if well_id in self.selected_wells:
            self.selected_wells.remove(well_id)
        else:
            self.selected_wells.add(well_id)
    
    def is_well_selected(self, well_id: str) -> bool:
        """Check if a well is selected"""
        return well_id in self.selected_wells
    
    def can_start_job(self) -> bool:
        """Check if job can be started"""
        return len(self.selected_wells) > 0 and not self.job_running
    
    def show_weight_dialog(self):
        """Show weight setting dialog"""
        if not self.selected_wells:
            self.show_error("Please select at least one well first.")
            return
        
        dialog = WeightDialog(self.selected_wells, self.well_weights)
        dialog.open()
    
    def start_job(self):
        """Start the dispensing job"""
        if not self.can_start_job():
            return
        
        # Show checklist first
        checklist = ChecklistDialog()
        checklist.bind(on_dismiss=self._on_checklist_dismiss)
        checklist.open()
    
    def _on_checklist_dismiss(self, instance):
        """Handle checklist dismissal"""
        if hasattr(instance, 'job_confirmed') and instance.job_confirmed:
            self._start_job_execution()
    
    def _start_job_execution(self):
        """Start the actual job execution"""
        self.job_running = True
        self.status_text = "Job running..."
        
        # Create job wells list
        self.job_wells = [
            JobWell(well_id=well_id, target_weight=self.well_weights.get(well_id, 0.0))
            for well_id in self.selected_wells
        ]
        
        # Start job in background thread
        self.current_job_thread = threading.Thread(target=self._job_thread, daemon=True)
        self.current_job_thread.start()
        
        # Show progress dialog
        self.show_progress_dialog()
    
    def _job_thread(self):
        """Background thread for job execution"""
        try:
            for i, job_well in enumerate(self.job_wells):
                if not self.job_running:
                    break
                
                # Update progress
                self.update_job_progress(i, len(self.job_wells), job_well.well_id)
                
                # Dispense to well using trickler
                # The trickler will handle scale monitoring internally
                success = self.jubilee_manager.dispense_to_well(job_well.well_id, job_well.target_weight)
                if not success:
                    self.show_error(f"Failed to dispense to well {job_well.well_id}")
                    return
                
                job_well.completed = True
                
                # Update progress after completion
                self.update_job_progress(i + 1, len(self.job_wells), f"Completed {job_well.well_id}")
            
            # Job completed
            Clock.schedule_once(lambda dt: self._job_completed(), 0)
            
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_error(f"Job error: {str(e)}"), 0)
        finally:
            Clock.schedule_once(lambda dt: setattr(self, 'job_running', False), 0)
    
    def update_job_progress(self, completed: int, total: int, current_well: str):
        """Update job progress (called from background thread)"""
        def update(dt):
            self.status_text = f"Processing {current_well} ({completed + 1}/{total})"
        Clock.schedule_once(update, 0)
    
    def _job_completed(self):
        """Handle job completion"""
        self.job_running = False
        self.status_text = "Job completed"
        self.show_finished_dialog()
    
    def stop_job(self):
        """Stop the current job"""
        self.job_running = False
        self.status_text = "Job stopped"
    
    def show_error(self, message: str):
        """Show error dialog"""
        dialog = ErrorDialog(error_message=message)
        dialog.open()
    
    def show_progress_dialog(self):
        """Show progress dialog"""
        dialog = ProgressDialog(
            completed_wells=0,
            total_wells=len(self.job_wells),
            current_well_text="Starting..."
        )
        dialog.bind(on_dismiss=self._on_progress_dismiss)
        dialog.open()
    
    def _on_progress_dismiss(self, instance):
        """Handle progress dialog dismissal"""
        self.stop_job()
    
    def show_finished_dialog(self):
        """Show job finished dialog"""
        dialog = FinishedDialog()
        dialog.open()

class WeightDialog(Popup):
    """Dialog for setting target weights"""
    
    def __init__(self, selected_wells: set, current_weights: dict, **kwargs):
        super().__init__(**kwargs)
        self.selected_wells = selected_wells
        self.current_weights = current_weights
        self.size_hint = (0.8, 0.8)
        self.title = "Set Target Weights"
        
        # Create weight inputs
        self._create_weight_inputs()
    
    def _create_weight_inputs(self):
        """Create weight input fields"""
        grid = self.ids.weight_inputs
        grid.clear_widgets()
        
        # Add header
        grid.add_widget(Label(text="Well", bold=True, size_hint_y=None, height=dp(40)))
        grid.add_widget(Label(text="Target Weight (g)", bold=True, size_hint_y=None, height=dp(40)))
        
        # Add inputs for each selected well
        for well_id in sorted(self.selected_wells):
            grid.add_widget(Label(text=well_id, size_hint_y=None, height=dp(40)))
            
            text_input = TextInput(
                text=str(self.current_weights.get(well_id, 0.0)),
                multiline=False,
                size_hint_y=None,
                height=dp(40),
                input_filter='float'
            )
            text_input.well_id = well_id
            grid.add_widget(text_input)
    
    def apply_weights(self):
        """Apply the entered weights"""
        grid = self.ids.weight_inputs
        new_weights = {}
        
        for child in grid.children:
            if isinstance(child, TextInput) and hasattr(child, 'well_id'):
                try:
                    weight = float(child.text)
                    new_weights[child.well_id] = weight
                except ValueError:
                    pass
        
        # Update main screen weights
        main_screen = self.parent.parent
        if hasattr(main_screen, 'well_weights'):
            main_screen.well_weights.update(new_weights)
        
        self.dismiss()

class ChecklistDialog(Popup):
    """Pre-job checklist dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.8, 0.8)
        self.title = "Pre-Job Checklist"
        self.job_confirmed = False
        
        self._create_checklist()
    
    def _create_checklist(self):
        """Create checklist items"""
        grid = self.ids.checklist_items
        grid.clear_widgets()
        
        # Add header
        grid.add_widget(Label(text="Check Item", bold=True, size_hint_y=None, height=dp(40)))
        grid.add_widget(Label(text="Status", bold=True, size_hint_y=None, height=dp(40)))
        
        # Checklist items
        checklist_items = [
            "Scale is connected and stable",
            "Trickler tool is loaded and calibrated",
            "Powder container is filled",
            "All target wells are clean and ready",
            "Emergency stop is accessible",
            "Work area is clear of obstructions"
        ]
        
        self.checkboxes = []
        for item in checklist_items:
            grid.add_widget(Label(text=item, size_hint_y=None, height=dp(40)))
            
            checkbox = CheckBox(size_hint_y=None, height=dp(40))
            self.checkboxes.append(checkbox)
            grid.add_widget(checkbox)
    
    def all_checked(self) -> bool:
        """Check if all items are checked"""
        return all(checkbox.active for checkbox in self.checkboxes)
    
    def start_job(self):
        """Start the job if all items are checked"""
        if self.all_checked():
            self.job_confirmed = True
            self.dismiss()
        else:
            # Show error or highlight unchecked items
            pass

class ProgressDialog(Popup):
    """Job progress dialog"""
    
    completed_wells = NumericProperty(0)
    total_wells = NumericProperty(1)
    progress_value = NumericProperty(0)
    current_well_text = StringProperty("")
    
    def __init__(self, completed_wells: int, total_wells: int, current_well_text: str, **kwargs):
        super().__init__(**kwargs)
        self.completed_wells = completed_wells
        self.total_wells = total_wells
        self.current_well_text = current_well_text
        self.size_hint = (0.8, 0.6)
        self.title = "Job Progress"
        
        # Update progress
        self.progress_value = (completed_wells / total_wells) * 100 if total_wells > 0 else 0
    
    def stop_job(self):
        """Stop the current job"""
        # This would need to communicate with the main screen
        self.dismiss()

class FinishedDialog(Popup):
    """Job finished dialog"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.6, 0.4)
        self.title = "Job Completed"

class ErrorDialog(Popup):
    """Error dialog"""
    
    error_message = StringProperty("")
    
    def __init__(self, error_message: str, **kwargs):
        super().__init__(**kwargs)
        self.error_message = error_message
        self.size_hint = (0.8, 0.6)
        self.title = "Error"

class JubileeGUIApp(App):
    """Main Jubilee GUI application"""
    
    def build(self):
        """Build the application"""
        # Create screen manager
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        return sm
    
    def on_stop(self):
        """Clean up when app stops"""
        # Disconnect from Jubilee system
        main_screen = self.root.get_screen('main')
        if hasattr(main_screen, 'jubilee_manager'):
            main_screen.jubilee_manager.disconnect()

if __name__ == '__main__':
    JubileeGUIApp().run() 