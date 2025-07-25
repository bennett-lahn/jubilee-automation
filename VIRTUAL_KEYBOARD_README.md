# Virtual Keyboard Integration for Jubilee GUI

This document explains how to use the virtual keyboard functionality in the Jubilee GUI application on Raspbian.

## Overview

The Jubilee GUI now includes automatic virtual keyboard management that:
- Shows the virtual keyboard when a text input field is focused
- Hides the keyboard when the text input loses focus
- Automatically detects available virtual keyboards on the system
- Provides touchscreen-friendly input for Raspberry Pi setups

## Installation

### 1. Install Virtual Keyboards

Run the installation script to install virtual keyboards:

```bash
chmod +x install_virtual_keyboard.sh
./install_virtual_keyboard.sh
```

Or install manually:

```bash
sudo apt update
sudo apt install matchbox-keyboard florence onboard xvkbd
```

### 2. Recommended Keyboard: matchbox-keyboard

`matchbox-keyboard` is recommended for touchscreen use because it:
- Has large, touch-friendly keys
- Supports multiple layouts
- Works well with Kivy applications
- Has good performance on Raspberry Pi

## How It Works

### Automatic Detection

The `VirtualKeyboardManager` class automatically detects available virtual keyboards:

1. **matchbox-keyboard** (recommended)
2. **florence** (alternative)
3. **onboard** (GNOME's virtual keyboard)
4. **xvkbd** (X11 virtual keyboard)

### Automatic Show/Hide

The `CustomTextInput` class automatically manages keyboard visibility:

- **Focus gained**: Keyboard appears automatically
- **Focus lost**: Keyboard hides after 0.5 seconds
- **Escape key**: Hides keyboard immediately
- **App pause**: Hides keyboard
- **App close**: Ensures keyboard is hidden

## Usage

### Using CustomTextInput

Replace regular `TextInput` widgets with `CustomTextInput`:

```python
from jubilee_gui import CustomTextInput

# Instead of:
# text_input = TextInput()

# Use:
text_input = CustomTextInput(
    text='',
    hint_text='Enter text...',
    size_hint_y=None,
    height=dp(60)
)
```

### Example Dialog

The `TextInputDialog` class demonstrates proper usage:

```python
def show_text_input_dialog(self):
    """Show text input dialog for testing virtual keyboard"""
    text_dialog = TextInputDialog()
    text_dialog.open()
```

### Testing the Keyboard

To test the virtual keyboard functionality:

1. Run the Jubilee GUI application
2. Call the text input dialog method (you can add a button to trigger it)
3. Tap on the text input field
4. The virtual keyboard should appear automatically
5. Type some text
6. Tap outside the text input or press Escape to hide the keyboard

## Configuration

### Keyboard Detection

The system automatically detects the first available keyboard in this order:
1. matchbox-keyboard
2. florence
3. onboard
4. xvkbd

### Customization

You can customize keyboard behavior by modifying the `VirtualKeyboardManager` class:

```python
# Change keyboard launch parameters
if self.keyboard_name == 'matchbox-keyboard':
    self.keyboard_process = subprocess.Popen([
        'matchbox-keyboard', '--xid', '--geometry', '800x300+0+0'
    ])
```

### Manual Control

You can manually control the keyboard:

```python
from jubilee_gui import keyboard_manager

# Show keyboard
keyboard_manager.show_keyboard()

# Hide keyboard
keyboard_manager.hide_keyboard()

# Check if keyboard is visible
if keyboard_manager.is_keyboard_visible():
    print("Keyboard is currently visible")
```

## Troubleshooting

### Keyboard Not Appearing

1. **Check installation**: Ensure virtual keyboards are installed
   ```bash
   which matchbox-keyboard
   ```

2. **Check permissions**: Ensure the application can launch external processes

3. **Check display**: Ensure the keyboard is launching on the correct display
   ```bash
   export DISPLAY=:0
   matchbox-keyboard
   ```

### Keyboard Not Hiding

1. **Check process**: The system uses `pkill` to terminate keyboard processes
2. **Manual kill**: If needed, manually kill keyboard processes
   ```bash
   pkill -f matchbox-keyboard
   ```

### Performance Issues

1. **Use matchbox-keyboard**: It's optimized for embedded systems
2. **Reduce delay**: Modify the hide delay in `CustomTextInput`
3. **Monitor processes**: Check for multiple keyboard instances

## Integration with Existing Dialogs

To add virtual keyboard support to existing dialogs:

1. Replace `TextInput` with `CustomTextInput`
2. The keyboard will automatically show/hide
3. No additional code changes needed

Example:

```python
# In WeightDialog._create_content()
self.weight_input = CustomTextInput(  # Changed from TextInput
    text='0.0',
    multiline=False,
    size_hint_y=None,
    height=dp(80),
    input_filter='float',
    halign='center',
    font_size=dp(32)
)
```

## Security Considerations

- The virtual keyboard runs as a separate process
- No sensitive data is stored by the keyboard manager
- Keyboard processes are properly terminated when the app closes
- Consider using secure input methods for password fields

## Future Enhancements

Potential improvements:
- Keyboard layout customization
- Multi-language support
- Keyboard positioning control
- Integration with system keyboard settings
- Support for additional keyboard types 