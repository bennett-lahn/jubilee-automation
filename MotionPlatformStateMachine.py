from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence

from statemachine import State, StateMachine


class PositionType(Enum):
    """Enumerates high-level motion platform positions."""

    GLOBAL_READY = auto()
    MOLD_READY = auto()
    DISPENSER_READY = auto()
    SCALE_READY = auto()


@dataclass(frozen=True)
class ZHeightPolicy:
    """Defines the z-height constraints that must be satisfied before a move."""

    allowed: frozenset[str] = field(default_factory=frozenset)
    required: Optional[str] = None

    def validate(self, z_height_id: Optional[str]) -> Optional[str]:
        """Return a human readable error message if the policy is not satisfied."""
        if (self.required or self.allowed) and z_height_id is None:
            return "Current z-height is not set."

        if self.required and z_height_id != self.required:
            current = "None" if z_height_id is None else z_height_id
            return f"Move requires z-height '{self.required}', current '{current}'."

        if self.allowed and z_height_id not in self.allowed:
            allowed = ", ".join(sorted(self.allowed))
            current = "None" if z_height_id is None else z_height_id
            return f"Z-height '{current}' not permitted. Allowed: {allowed}."

        return None


@dataclass(frozen=True)
class MachineCoordinates:
    """Physical X, Y, Z, V coordinates for a position."""
    
    x: Optional[float | str] = None
    y: Optional[float | str] = None
    z: Optional[float | str] = None  # Can be "USE_Z_HEIGHT_POLICY" or numeric
    v: Optional[float | str] = None


@dataclass(frozen=True)
class PositionDescriptor:
    """
    Describes a logical position that the motion platform can occupy.

    Positions extend beyond XYZ coordinates and capture the holistic machine
    pose, including manipulator states, payload status, or ancillary actuator
    configurations.
    """

    identifier: str
    type: PositionType
    allowed_origins: frozenset[str]
    allowed_destinations: frozenset[str]
    coordinates: Optional[MachineCoordinates] = None
    requirements: Mapping[str, object] = field(default_factory=dict)
    z_height_policy: ZHeightPolicy = field(default_factory=ZHeightPolicy)
    allows_tool_engagement: bool = False
    engagement_requirements: Mapping[str, object] = field(default_factory=dict)
    engagement_actions: frozenset[str] = field(default_factory=frozenset)
    resource_id: Optional[str] = None
    description: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDescriptor:
    """Represents an auxiliary action that can be validated by the FSM."""

    identifier: str
    position_scope: frozenset[str]
    requirements: Mapping[str, object] = field(default_factory=dict)
    excludes: Mapping[str, object] = field(default_factory=dict)
    required_tool_id: Optional[str] = None
    requires_tool_engaged: bool = False
    blocked_when_engaged: bool = False
    description: str = ""


@dataclass
class ToolStatus:
    """Tracks engagement state and the ready point associated with a tool."""

    tool_id: str
    engaged: bool = False
    ready_position_id: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MotionContext:
    """Captures the mutable state of the motion platform."""

    position_id: str
    z_height_id: Optional[str] = None
    active_tool_id: Optional[str] = None
    payload_state: Optional[str] = None
    tool_pose: Optional[str] = None
    tool_states: Dict[str, ToolStatus] = field(default_factory=dict)
    pending_move: Optional["MoveRequest"] = None
    engaged_ready_position_id: Optional[str] = None
    engaged_tool_id: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MoveRequest:
    """Represents a requested transition for the motion platform."""

    target_position_id: str
    action: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MoveValidationResult:
    """Encapsulates the outcome of a move validation."""

    valid: bool
    reason: Optional[str] = None


class PositionRegistry:
    """Utility container for known platform positions."""

    def __init__(self, positions: Iterable[PositionDescriptor]) -> None:
        self._positions: Dict[str, PositionDescriptor] = {}
        self._actions: Dict[str, ActionDescriptor] = {}
        self._z_heights: Dict[str, object] = {}
        self._coordinate_tolerance: Dict[str, float] = {
            "x": 0.5,
            "y": 0.5,
            "z": 0.5,
            "v": 0.5,
        }

        for position in positions:
            self.add_position(position)

    @classmethod
    def from_config_file(cls, path: str | Path) -> "PositionRegistry":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        # First pass: collect all positions to build type-to-id mapping
        positions: list[PositionDescriptor] = []
        type_to_ids: Dict[str, set[str]] = {}
        
        for raw in payload.get("positions", []):
            try:
                position_type = PositionType[raw["type"]]
            except KeyError as exc:
                raise KeyError(f"Unknown position type '{raw['type']}'") from exc

            position_id = raw["id"]
            type_name = raw["type"]
            
            if type_name not in type_to_ids:
                type_to_ids[type_name] = set()
            type_to_ids[type_name].add(position_id)

            z_policy_config = raw.get("z_height_policy", {})
            z_policy = ZHeightPolicy(
                allowed=frozenset(z_policy_config.get("allowed", [])),
                required=z_policy_config.get("required"),
            )

            engagement_cfg = raw.get("engagement") or {}
            
            # Parse coordinates if present
            coords_cfg = raw.get("coordinates")
            coordinates = None
            if coords_cfg:
                coordinates = MachineCoordinates(
                    x=coords_cfg.get("x"),
                    y=coords_cfg.get("y"),
                    z=coords_cfg.get("z"),
                    v=coords_cfg.get("v"),
                )

            # Store raw origins/destinations for now
            descriptor = PositionDescriptor(
                identifier=position_id,
                type=position_type,
                allowed_origins=frozenset(raw.get("allowed_origins", [])),
                allowed_destinations=frozenset(raw.get("allowed_destinations", [])),
                coordinates=coordinates,
                requirements=dict(raw.get("requirements", {})),
                z_height_policy=z_policy,
                allows_tool_engagement=raw.get("allows_tool_engagement", False),
                engagement_requirements=dict(engagement_cfg.get("requirements", {})),
                engagement_actions=frozenset(engagement_cfg.get("allowed_actions", [])),
                resource_id=raw.get("resource_id"),
                description=raw.get("description", ""),
                metadata=dict(raw.get("metadata", {})),
            )
            positions.append(descriptor)

        # Second pass: expand type references to actual position IDs
        def expand_references(refs: frozenset[str]) -> frozenset[str]:
            """Expand type names (e.g., 'MOLD_READY') to all position IDs of that type."""
            expanded = set()
            for ref in refs:
                if ref in type_to_ids:
                    # It's a type reference, expand to all IDs of that type
                    expanded.update(type_to_ids[ref])
                else:
                    # It's a specific position ID
                    expanded.add(ref)
            return frozenset(expanded)

        # Update all descriptors with expanded references
        expanded_positions = []
        for descriptor in positions:
            expanded_descriptor = PositionDescriptor(
                identifier=descriptor.identifier,
                type=descriptor.type,
                allowed_origins=expand_references(descriptor.allowed_origins),
                allowed_destinations=expand_references(descriptor.allowed_destinations),
                coordinates=descriptor.coordinates,
                requirements=descriptor.requirements,
                z_height_policy=descriptor.z_height_policy,
                allows_tool_engagement=descriptor.allows_tool_engagement,
                engagement_requirements=descriptor.engagement_requirements,
                engagement_actions=descriptor.engagement_actions,
                resource_id=descriptor.resource_id,
                description=descriptor.description,
                metadata=descriptor.metadata,
            )
            expanded_positions.append(expanded_descriptor)

        registry = cls(expanded_positions)
        registry._actions = {
            action_cfg["id"]: ActionDescriptor(
                identifier=action_cfg["id"],
                position_scope=frozenset(action_cfg.get("position_scope", [])),
                requirements=dict(action_cfg.get("requirements", {})),
                excludes=dict(action_cfg.get("excludes", {})),
                required_tool_id=action_cfg.get("required_tool_id"),
                requires_tool_engaged=action_cfg.get("requires_tool_engaged", False),
                blocked_when_engaged=action_cfg.get("blocked_when_engaged", False),
                description=action_cfg.get("description", ""),
            )
            for action_cfg in payload.get("actions", [])
        }
        registry._z_heights = dict(payload.get("z_heights", {}))
        
        # Load coordinate tolerance if present
        if "coordinate_tolerance" in payload:
            tolerance_cfg = payload["coordinate_tolerance"]
            registry._coordinate_tolerance = {
                "x": tolerance_cfg.get("x", 0.5),
                "y": tolerance_cfg.get("y", 0.5),
                "z": tolerance_cfg.get("z", 0.5),
                "v": tolerance_cfg.get("v", 0.5),
            }
        
        return registry

    def add_position(self, position: PositionDescriptor) -> None:
        if position.identifier in self._positions:
            raise ValueError(f"Duplicate position identifier '{position.identifier}'")
        self._positions[position.identifier] = position

    def get(self, identifier: str) -> PositionDescriptor:
        try:
            return self._positions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown position identifier '{identifier}'") from exc

    def has(self, identifier: str) -> bool:
        return identifier in self._positions

    def find_first_of_type(self, position_type: PositionType) -> Optional[PositionDescriptor]:
        for descriptor in self._positions.values():
            if descriptor.type == position_type:
                return descriptor
        return None

    def get_action(self, identifier: str) -> ActionDescriptor:
        try:
            return self._actions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown action identifier '{identifier}'") from exc

    @property
    def actions(self) -> Dict[str, ActionDescriptor]:
        return dict(self._actions)

    @property
    def z_heights(self) -> Dict[str, object]:
        return dict(self._z_heights)
    
    @property
    def coordinate_tolerance(self) -> Dict[str, float]:
        return dict(self._coordinate_tolerance)
    
    def validate_machine_position(
        self,
        position_id: str,
        machine_x: float,
        machine_y: float,
        machine_z: float,
        machine_v: float,
        current_z_height_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Validate that the machine is actually at the expected coordinates for a position.
        
        Returns None if validation passes, or an error message if coordinates don't match.
        """
        position = self.get(position_id)
        if not position.coordinates:
            # No coordinates defined for this position, skip validation
            return None
        
        coords = position.coordinates
        tolerance = self._coordinate_tolerance
        
        def check_coord(axis: str, expected: Optional[float | str], actual: float) -> Optional[str]:
            """Check if a single coordinate is within tolerance."""
            if expected is None:
                return None
            
            # Handle placeholder strings
            if isinstance(expected, str):
                if expected.startswith("PLACEHOLDER"):
                    # Placeholder not yet filled in, skip validation
                    return None
                if expected == "USE_Z_HEIGHT_POLICY":
                    # Special case: Z coord comes from z_height policy
                    if current_z_height_id is None:
                        return f"Z coordinate requires z_height_id but none provided"
                    if current_z_height_id not in self._z_heights:
                        return f"Unknown z_height_id: {current_z_height_id}"
                    z_config = self._z_heights[current_z_height_id]
                    if isinstance(z_config, dict):
                        z_expected = z_config.get("z_coordinate")
                        if z_expected and isinstance(z_expected, (int, float)):
                            if abs(actual - z_expected) > tolerance[axis]:
                                return f"{axis.upper()} coordinate mismatch: expected {z_expected}, got {actual} (tolerance: ±{tolerance[axis]})"
                    return None
            
            # Numeric comparison
            if isinstance(expected, (int, float)):
                if abs(actual - expected) > tolerance[axis]:
                    return f"{axis.upper()} coordinate mismatch: expected {expected}, got {actual} (tolerance: ±{tolerance[axis]})"
            
            return None
        
        # Check each axis
        for axis, expected, actual in [
            ("x", coords.x, machine_x),
            ("y", coords.y, machine_y),
            ("z", coords.z, machine_z),
            ("v", coords.v, machine_v),
        ]:
            error = check_coord(axis, expected, actual)
            if error:
                return f"Position '{position_id}' validation failed: {error}"
        
        return None


class MotionPlatformStateMachine(StateMachine):
    """
    Finite state machine responsible for validating and sequencing platform moves.

    The machine relies on python-statemachine to model the control flow. It
    maintains awareness of both high-level state (idle, moving, tool engaged)
    and the current logical position descriptor.
    """

    idle = State("Idle", initial=True)
    moving = State("Moving")
    tool_engaged = State("Tool Engaged")

    begin_motion = idle.to(moving)
    complete_motion = moving.to(idle)
    engage_tool = idle.to(tool_engaged)
    disengage_tool = tool_engaged.to(idle)
    abort_motion = moving.to(idle)

    def __init__(self, registry: PositionRegistry, *, context: Optional[MotionContext] = None) -> None:
        self._registry = registry
        self._actions = registry.actions

        if context is None:
            initial_descriptor = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if not initial_descriptor:
                raise ValueError("Configuration must define a GLOBAL_READY position.")
            context = MotionContext(position_id=initial_descriptor.identifier)
        else:
            # Ensure the provided context references a known position.
            self._registry.get(context.position_id)

        self.context = context
        super().__init__()

    @classmethod
    def from_config_file(
        cls,
        path: str | Path,
        *,
        context_overrides: Optional[Mapping[str, object]] = None,
    ) -> "MotionPlatformStateMachine":
        registry = PositionRegistry.from_config_file(path)
        initial_descriptor = registry.find_first_of_type(PositionType.GLOBAL_READY)
        if not initial_descriptor:
            raise ValueError("Configuration must include a GLOBAL_READY position.")

        context_kwargs = dict(
            position_id=initial_descriptor.identifier,
            z_height_id=None,
            active_tool_id=None,
            payload_state=None,
            tool_pose=None,
            tool_states={},
            pending_move=None,
            engaged_ready_position_id=None,
            engaged_tool_id=None,
            metadata={},
        )

        if context_overrides:
            context_kwargs.update(context_overrides)

        context = MotionContext(**context_kwargs)
        return cls(registry, context=context)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def request_move(self, request: MoveRequest) -> MoveValidationResult:
        """
        Evaluate and, if permissible, initiate a move or action.

        If the request references an action, the FSM validates the action without
        changing state. Otherwise, the FSM transitions into the moving state and
        records the pending move for completion tracking.
        """
        if request.action:
            return self.perform_action(request.action)

        if self.current_state == self.moving:
            return MoveValidationResult(valid=False, reason="Already executing a move.")

        validation = self.validate_move(request)
        if not validation.valid:
            return validation

        self.context.pending_move = request
        self.begin_motion()
        return validation

    def perform_action(self, action_id: str) -> MoveValidationResult:
        """Validate whether an auxiliary action is permitted."""
        descriptor = self._actions.get(action_id)
        if descriptor is None:
            return MoveValidationResult(valid=False, reason=f"Unknown action '{action_id}'.")

        # Check if action requires tool engagement (e.g., trickler_dispense)
        if descriptor.requires_tool_engaged and self.current_state != self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=f"Action '{action_id}' requires the tool to be engaged.",
            )

        # Check if action is blocked when tool is engaged (most actions)
        if descriptor.blocked_when_engaged and self.current_state == self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Action '{action_id}' cannot be performed while tool is engaged. "
                    f"Tool must be disengaged first."
                ),
            )

        if descriptor.required_tool_id:
            if self.context.active_tool_id != descriptor.required_tool_id:
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' requires tool '{descriptor.required_tool_id}'. "
                        f"Current tool: '{self.context.active_tool_id}'."
                    ),
                )

        if descriptor.position_scope:
            reference_position = (
                self.context.engaged_ready_position_id
                if self.current_state == self.tool_engaged
                else self.context.position_id
            )
            if reference_position not in descriptor.position_scope:
                allowed = self._format_options(descriptor.position_scope)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' only permitted at: {allowed}. "
                        f"Current position: '{reference_position}'."
                    ),
                )

        requirement_issue = self._validate_requirements(descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        exclude_issue = self._validate_excludes(descriptor.excludes)
        if exclude_issue:
            return MoveValidationResult(valid=False, reason=exclude_issue)

        return MoveValidationResult(valid=True)

    def validate_move(self, request: MoveRequest) -> MoveValidationResult:
        """
        Core validation hook for requested moves.

        This implementation verifies:
          * The target position exists in the registry.
          * The transition between current and target positions is permitted.
          * Z-height and contextual requirements are satisfied.
          * Engaged tools remain constrained to their ready points.
        """
        try:
            target_descriptor = self._registry.get(request.target_position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Unknown target position '{request.target_position_id}'.",
            )

        try:
            current_descriptor = self._registry.get(self.context.position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Current position '{self.context.position_id}' is not registered.",
            )

        if self.current_state == self.tool_engaged:
            if request.target_position_id != self.context.position_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Cannot leave the ready point while the tool is engaged.",
                )
        else:
            if request.target_position_id not in current_descriptor.allowed_destinations:
                allowed = self._format_options(current_descriptor.allowed_destinations)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Cannot move from '{self.context.position_id}' to "
                        f"'{request.target_position_id}'. Allowed destinations: {allowed}."
                    ),
                )

            if self.context.position_id not in target_descriptor.allowed_origins:
                allowed_origins = self._format_options(target_descriptor.allowed_origins)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"'{request.target_position_id}' cannot accept moves from "
                        f"'{self.context.position_id}'. Allowed origins: {allowed_origins}."
                    ),
                )

        if self.current_state != self.tool_engaged:
            z_height_issue = target_descriptor.z_height_policy.validate(self.context.z_height_id)
            if z_height_issue:
                return MoveValidationResult(valid=False, reason=z_height_issue)

        requirement_issue = self._validate_requirements(target_descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        return MoveValidationResult(valid=True)

    def complete_move(self, *, tool_still_engaged: bool) -> None:
        """
        Finalize a move previously initiated via `request_move`.

        Args:
            tool_still_engaged: Indicates whether the tool engagement status
                should keep the FSM in the tool_engaged state after the move.
        """
        if not self.context.pending_move:
            raise RuntimeError("Cannot complete move when no pending move is recorded.")

        target_position = self._registry.get(self.context.pending_move.target_position_id)
        self.context.position_id = target_position.identifier

        if tool_still_engaged:
            self.context.engaged_ready_position_id = target_position.identifier
            if not self.context.engaged_tool_id:
                self.context.engaged_tool_id = self.context.active_tool_id
            self.complete_motion_with_tool()
        else:
            self._assert_engagement_exit_ready()
            self.complete_motion()
            self.context.engaged_ready_position_id = None
            self.context.engaged_tool_id = None

        self.context.pending_move = None

    def request_tool_engagement(self) -> MoveValidationResult:
        """Attempt to transition from idle to tool engaged state at the current position."""
        if self.current_state != self.idle:
            return MoveValidationResult(
                valid=False,
                reason="Tool engagement is only permitted while idle at a ready point.",
            )

        descriptor = self._registry.get(self.context.position_id)
        if not descriptor.allows_tool_engagement:
            return MoveValidationResult(
                valid=False,
                reason=f"Tool engagement is not permitted at '{descriptor.identifier}'.",
            )

        requirements = descriptor.engagement_requirements or descriptor.requirements
        requirement_issue = self._validate_requirements(requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        self.engage_tool()
        self.context.engaged_ready_position_id = descriptor.identifier
        self.context.engaged_tool_id = self.context.active_tool_id
        return MoveValidationResult(valid=True)

    def request_tool_disengagement(self) -> MoveValidationResult:
        """Attempt to disengage the tool and return to idle."""
        if self.current_state != self.tool_engaged:
            return MoveValidationResult(valid=False, reason="No tool is currently engaged.")

        if not self.context.engaged_ready_position_id:
            return MoveValidationResult(
                valid=False,
                reason="Engaged ready position is unknown; cannot disengage safely.",
            )

        descriptor = self._registry.get(self.context.engaged_ready_position_id)
        requirements = descriptor.engagement_requirements or descriptor.requirements
        requirement_issue = self._validate_requirements(requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        self.disengage_tool()
        self.context.engaged_ready_position_id = None
        self.context.engaged_tool_id = None
        return MoveValidationResult(valid=True)

    def register_tool(self, tool_status: ToolStatus) -> None:
        """Introduce or update a tool within the motion context."""
        self.context.tool_states[tool_status.tool_id] = tool_status

    def update_tool_engagement(self, tool_id: str, engaged: bool) -> None:
        """Update the engagement flag for a specific tool."""
        if tool_id not in self.context.tool_states:
            raise KeyError(f"Tool '{tool_id}' is not registered.")
        self.context.tool_states[tool_id].engaged = engaged

    def update_context(
        self,
        *,
        active_tool_id: Optional[str] = None,
        payload_state: Optional[str] = None,
        tool_pose: Optional[str] = None,
        z_height_id: Optional[str] = None,
    ) -> None:
        """Convenience helper to mutate commonly updated context properties."""
        if active_tool_id is not None:
            self.context.active_tool_id = active_tool_id
        if payload_state is not None:
            self.context.payload_state = payload_state
        if tool_pose is not None:
            self.context.tool_pose = tool_pose
        if z_height_id is not None:
            self.context.z_height_id = z_height_id
    
    def validate_machine_state(
        self,
        machine_x: float,
        machine_y: float,
        machine_z: float,
        machine_v: float,
    ) -> MoveValidationResult:
        """
        Validate that the machine's physical coordinates match the FSM's expected position.
        
        This is a safety check to ensure the machine is actually where the FSM thinks it is.
        Should be called before attempting moves or actions.
        
        Args:
            machine_x: Current X coordinate from machine
            machine_y: Current Y coordinate from machine
            machine_z: Current Z coordinate from machine
            machine_v: Current V (manipulator) coordinate from machine
            
        Returns:
            MoveValidationResult indicating if machine state matches expected position
        """
        error = self._registry.validate_machine_position(
            position_id=self.context.position_id,
            machine_x=machine_x,
            machine_y=machine_y,
            machine_z=machine_z,
            machine_v=machine_v,
            current_z_height_id=self.context.z_height_id,
        )
        
        if error:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Machine state validation failed: {error}. "
                    f"Machine may not be at expected position '{self.context.position_id}'."
                ),
            )
        
        return MoveValidationResult(valid=True)

    # ---------------------------------------------------------------------
    # FSM Lifecycle Hooks
    # ---------------------------------------------------------------------
    def on_enter_moving(self) -> None:
        """
        Hook invoked when entering the moving state.

        Future implementations can trigger hardware-level commands or logging
        from this hook. The current framework simply asserts that a pending move
        exists when transitions occur.
        """
        if not self.context.pending_move:
            raise RuntimeError("Entered moving state without a pending move.")

    def on_enter_idle(self) -> None:
        """Reset pending move tracking when returning to idle."""
        self.context.pending_move = None

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _assert_engagement_exit_ready(self) -> None:
        """Ensure the machine satisfies engagement requirements before exiting."""
        if not self.context.engaged_ready_position_id:
            return

        descriptor = self._registry.get(self.context.engaged_ready_position_id)
        requirements = descriptor.engagement_requirements or descriptor.requirements
        issue = self._validate_requirements(requirements)
        if issue:
            raise RuntimeError(f"Cannot exit tool-engaged state: {issue}")

    def _validate_requirements(self, requirements: Mapping[str, object]) -> Optional[str]:
        """Validate context attributes against a requirements mapping."""
        for key, expected in requirements.items():
            actual = getattr(self.context, key, None)
            if not self._value_matches(actual, expected):
                expected_display = (
                    self._format_options(expected)
                    if isinstance(expected, (list, tuple, set, frozenset))
                    else repr(expected)
                )
                return (
                    f"Requirement '{key}={expected_display}' not satisfied "
                    f"(current: {repr(actual)})."
                )
        return None

    def _validate_excludes(self, excludes: Mapping[str, object]) -> Optional[str]:
        """Validate that context attributes do not match excluded values."""
        for key, excluded in excludes.items():
            actual = getattr(self.context, key, None)
            if self._value_matches(actual, excluded):
                excluded_display = (
                    self._format_options(excluded)
                    if isinstance(excluded, (list, tuple, set, frozenset))
                    else repr(excluded)
                )
                return (
                    f"Exclusion violated: '{key}' must not be {excluded_display} "
                    f"(current: {repr(actual)})."
                )
        return None

    @staticmethod
    def _value_matches(actual: object, expected: object) -> bool:
        """Determine whether a context value satisfies an expected requirement."""
        if isinstance(expected, (list, tuple, set, frozenset)):
            return actual in expected
        return actual == expected

    @staticmethod
    def _format_options(options: Sequence[str] | Iterable[str]) -> str:
        """Render a collection of options as a comma-separated string."""
        return ", ".join(sorted({str(option) for option in options}))
