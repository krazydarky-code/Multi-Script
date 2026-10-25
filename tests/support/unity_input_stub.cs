// Minimal stand-in for the Unity Input System package API surface used by the generated scripts.
// Only used to compile-check the `#if ENABLE_INPUT_SYSTEM && !ENABLE_LEGACY_INPUT_MANAGER` branches.
namespace UnityEngine.InputSystem
{
    public class ButtonControl { public bool isPressed { get { return false; } } public bool wasPressedThisFrame { get { return false; } } }
    public class StickControl { public Vector2 ReadValue() { return Vector2.zero; } }
    public class Vector2Control { public Vector2 ReadValue() { return Vector2.zero; } }
    public class Keyboard
    {
        public static Keyboard current { get { return null; } }
        public ButtonControl wKey, aKey, sKey, dKey, upArrowKey, downArrowKey, leftArrowKey, rightArrowKey, spaceKey, leftShiftKey, eKey, escapeKey, f5Key, f9Key;
    }
    public class Mouse { public static Mouse current { get { return null; } } public ButtonControl leftButton; public Vector2Control delta; }
    public class Gamepad
    {
        public static Gamepad current { get { return null; } }
        public StickControl leftStick, rightStick; public ButtonControl buttonSouth, buttonWest, leftStickButton, startButton, rightTrigger;
    }
}