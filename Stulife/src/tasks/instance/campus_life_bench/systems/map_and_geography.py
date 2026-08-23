"""
Map and Geography System for CampusLifeBench
All natural language communications/returns MUST use English only
"""

import json
import heapq
import itertools
import re
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

from ..tools import ensure_english_message


@dataclass
class GeographyState:
    """Current geography state of the agent"""
    current_location_id: str
    current_location_name: str
    walk_history: List[List[str]]


class MapLookupSystem:
    """
    Static map information lookup system
    Provides read-only access to campus map data
    """

    def __init__(self, map_data_path: Path):
        """
        Initialize map lookup system

        Args:
            map_data_path: Path to map data JSON file
        """
        self.map_data_path = map_data_path
        self._map_data: Optional[Dict[str, Any]] = None
        self._load_map_data()

    def _load_map_data(self):
        """Load map data from JSON file"""
        try:
            with open(self.map_data_path, 'r', encoding='utf-8') as f:
                self._map_data = json.load(f)
        except FileNotFoundError:
            # Create minimal map data if file doesn't exist
            self._map_data = {
                "nodes": [
                    {
                        "id": "B083",
                        "name": "Lakeside Dormitory",
                        "aliases": ["Dorm", "Dormitory"],
                        "type": "Residential",
                        "zone": "Residential Area",
                        "internal_amenities": {
                            "floor_1": ["Lobby", "Common Room"],
                            "floor_2": ["Student Rooms (201-220)"]
                        }
                    }
                ],
                "edges": [],
                "building_complexes": []
            }

    def _get_node(self, building_id: str) -> dict:
        """
        Get the node dict for a building ID.

        Args:
            building_id: Building ID to look up

        Returns:
            Node dictionary

        Raises:
            ValueError: If building_id is not found
        """
        for node in self._map_data["nodes"]:
            if node["id"] == building_id:
                return node
        raise ValueError(f"Building with ID '{building_id}' not found.")

    def find_building_id(self, building_name: str) -> Dict[str, str]:
        """
        Find building ID by name or alias

        Args:
            building_name: Building name or alias to search for

        Returns:
            Dict with "name" and "id" keys.

        Raises:
            ValueError: If building name is missing or not found
        """
        if not building_name:
            raise ValueError("Building name is required.")

        # Try both with and without "The " prefix — task descriptions sometimes
        # use a grammatical lowercase "the" that doesn't match canonical names
        # like "The Capitol Forum", or vice versa.
        candidates = [building_name.lower()]
        if building_name.lower().startswith("the "):
            candidates.append(building_name[4:].lower())
        else:
            candidates.append(("the " + building_name).lower())

        for node in self._map_data["nodes"]:
            node_name_lower = node["name"].lower()
            if node_name_lower in candidates:
                return {"name": node["name"], "id": node["id"]}

            for alias in node.get("aliases", []):
                if alias.lower() in candidates:
                    return {"name": node["name"], "id": node["id"]}

        raise ValueError(f"Building '{building_name}' not found.")

    def get_building_details(self, building_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a building

        Args:
            building_id: Building ID to get details for

        Returns:
            Dict with building_id, name, type, zone, aliases, and internal_amenities

        Raises:
            ValueError: If building_id is missing or not found
        """
        if not building_id:
            raise ValueError("Building ID is required.")

        # Validate building ID format (all IDs are "B" + 3 digits, e.g. "B001").
        if not re.match(r'^B\d{3}$', building_id):
            raise ValueError(
                f"Invalid building ID '{building_id}'. "
                f"Building IDs have the format 'B' + 3 digits (e.g. 'B001'). "
                f"Use find_building_id() to look up a building's ID by name."
            )

        for node in self._map_data["nodes"]:
            if node["id"] == building_id:
                return {
                    "building_id": building_id,
                    "name": node['name'],
                    "type": node.get('type', 'Unknown'),
                    "zone": node.get('zone', 'Unknown'),
                    "aliases": node.get('aliases', []),
                    "internal_amenities": node.get('internal_amenities', {}),
                }

        raise ValueError(f"Building with ID '{building_id}' not found.")

    def find_room_location(self, room_query: str, building_id: Optional[str] = None, zone: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Find room location within campus or specified area

        Args:
            room_query: Room name or number to search for
            building_id: Optional building ID to limit search
            zone: Optional zone to limit search

        Returns:
            List of dicts with building_id, building_name, floor, and room_name.
            Returns an empty list if no matches are found.

        Raises:
            ValueError: If room_query is missing
        """
        if not room_query:
            raise ValueError("Room query is required.")

        room_query_lower = room_query.lower()
        found_rooms: List[Dict[str, str]] = []

        for node in self._map_data["nodes"]:
            # Apply filters
            if building_id and node["id"] != building_id:
                continue
            if zone and node.get("zone") != zone:
                continue

            # Search in internal amenities
            for floor, items in node.get("internal_amenities", {}).items():
                for item in items:
                    if room_query_lower in item.lower():
                        found_rooms.append({
                            "building_id": node["id"],
                            "building_name": node["name"],
                            "floor": floor,
                            "room_name": item
                        })

        return found_rooms

    def find_optimal_path(self, source_building_id: str, target_building_id: str, constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Find optimal path between two buildings using deterministic algorithm.

        Returns a dict with ``path`` (list of building IDs) and ``path_names``
        (list of building names) so the caller can pass the result directly to
        ``walk_to``.

        Raises:
            ValueError: If inputs are missing or no path found
        """
        if not all([source_building_id, target_building_id]):
            raise ValueError("Both source and target building IDs are required.")

        # Validate building ID format (all IDs are "B" + 3 digits, e.g. "B001").
        for arg_name, bid in [("source", source_building_id), ("target", target_building_id)]:
            if not re.match(r'^B\d{3}$', bid):
                raise ValueError(
                    f"Invalid {arg_name} building ID '{bid}'. "
                    f"Building IDs have the format 'B' + 3 digits (e.g. 'B001'). "
                    f"Use find_building_id() to look up a building's ID by name."
                )

        # Validate building IDs exist in the map.
        node_ids = {node['id'] for node in self._map_data['nodes']}
        for arg_name, bid in [("source", source_building_id), ("target", target_building_id)]:
            if bid not in node_ids:
                raise ValueError(f"Building '{bid}' does not exist.")

        if constraints is None:
            constraints = {}

        # Validate constraint keys/values against the edge properties actually present in the map, so a
        # typo (silently ignored by the cost function, which just penalizes every edge uniformly) fails
        # fast instead of returning an unconstrained path the caller believes was constrained.
        if constraints:
            valid: Dict[str, set] = {}
            for edge in self._map_data.get("edges", []):
                for k, v in (edge.get("properties") or {}).items():
                    valid.setdefault(k, set()).add(v)
            for k, v in constraints.items():
                if k not in valid:
                    raise ValueError(
                        f"Unknown constraint key '{k}'. Valid keys: {sorted(valid)}."
                    )
                if v not in valid[k]:
                    raise ValueError(
                        f"Invalid value '{v}' for constraint '{k}'. Valid values: {sorted(valid[k])}."
                    )

        result = self._find_optimal_path_algorithm(self._map_data, source_building_id, target_building_id, constraints)

        if "error" in result:
            raise ValueError(result["error"])

        path = result["path"]
        path_names = []
        for building_id in path:
            for node in self._map_data["nodes"]:
                if node["id"] == building_id:
                    path_names.append(node["name"])
                    break
            else:
                # TODO: should use _get_node() and let it raise instead of silently falling back to the ID
                path_names.append(building_id)

        return {"path": path, "path_names": path_names}

    def _find_optimal_path_algorithm(self, map_data, source_id, target_id, constraints=None):
        """
        Deterministic path finding algorithm (from find_optimal_path.py)
        """
        if constraints is None:
            constraints = {}

        nodes = {node['id']: node for node in map_data['nodes']}

        if source_id not in nodes:
            return {"error": f"No path could be found from {source_id} to {target_id}."}
        if target_id not in nodes:
            return {"error": f"No path could be found from {source_id} to {target_id}."}

        graph = {node_id: [] for node_id in nodes}
        for edge in map_data.get('edges', []):
            source, target = edge.get('source'), edge.get('target')
            if source in nodes and target in nodes:
                properties = edge.get('properties', {})
                time_cost = edge.get('time_cost', 0)
                properties['is_complex_path'] = False
                graph[source].append((target, time_cost, properties))
                graph[target].append((source, time_cost, properties))

        for complex_group in map_data.get('building_complexes', []):
            member_ids = complex_group.get('member_ids', [])
            for u, v in itertools.combinations(member_ids, 2):
                if u in nodes and v in nodes:
                    properties = {'is_complex_path': True}
                    time_cost = 0
                    graph[u].append((v, time_cost, properties))
                    graph[v].append((u, time_cost, properties))

        # Core algorithm with dynamic penalty logic
        PENALTY_MULTIPLIER = 0.5

        priority_queue = [(0, 1, 0, source_id, [source_id])]
        visited_costs = {}

        while priority_queue:
            priority_cost, path_len, real_time_cost, current_node, path = heapq.heappop(priority_queue)

            if current_node in visited_costs and visited_costs[current_node] <= (priority_cost, path_len):
                continue

            visited_costs[current_node] = (priority_cost, path_len)

            if current_node == target_id:
                return {"path": path, "total_time_cost": real_time_cost}

            for neighbor, edge_time, properties in graph.get(current_node, []):

                unmet_constraints = 0
                if not properties.get('is_complex_path', False):
                    for key, required_value in constraints.items():
                        edge_value = properties.get(key)

                        is_violated = False
                        if edge_value is None:
                            is_violated = True
                        elif key == 'rain_exposure' and required_value == 'Covered' and 'Exposed' in edge_value:
                            is_violated = True
                        elif key != 'rain_exposure' and edge_value != required_value:
                            is_violated = True

                        if is_violated:
                            unmet_constraints += 1

                base_cost = edge_time if edge_time > 0 else 0.01
                cost_multiplier = 1 + (unmet_constraints * PENALTY_MULTIPLIER)
                effective_edge_cost = base_cost * cost_multiplier

                new_priority_cost = priority_cost + effective_edge_cost
                new_real_time_cost = real_time_cost + edge_time
                new_path_len = path_len + 1

                if neighbor not in visited_costs or (new_priority_cost, new_path_len) < visited_costs[neighbor]:
                    heapq.heappush(priority_queue, (new_priority_cost, new_path_len, new_real_time_cost, neighbor, path + [neighbor]))

        return {"error": f"No path could be found from {source_id} to {target_id}."}

    def query_buildings_by_property(self, zone: Optional[str] = None, building_type: Optional[str] = None, amenity: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query buildings by properties

        Args:
            zone: Zone to filter by
            building_type: Building type to filter by
            amenity: Amenity to filter by

        Returns:
            List of dicts with building_id, name, type, and zone

        Raises:
            ValueError: If no buildings match the criteria
        """
        matching_buildings: List[Dict[str, Any]] = []

        for node in self._map_data["nodes"]:
            # Apply filters
            if zone and node.get("zone") != zone:
                continue
            if building_type and node.get("type") != building_type:
                continue
            if amenity:
                # Search in internal amenities
                found_amenity = False
                for floor, items in node.get("internal_amenities", {}).items():
                    if any(amenity.lower() in item.lower() for item in items):
                        found_amenity = True
                        break
                if not found_amenity:
                    continue

            matching_buildings.append({
                "building_id": node["id"],
                "name": node["name"],
                "type": node.get("type"),
                "zone": node.get("zone")
            })

        if not matching_buildings:
            raise ValueError("No buildings found matching the specified criteria.")

        return matching_buildings

    def get_building_complex_info(self, building_id: str) -> Dict[str, Any]:
        """
        Get building complex information

        Args:
            building_id: Building ID to check for complex membership

        Returns:
            Dict with is_complex_member, complex_name, and member_ids

        Raises:
            ValueError: If building_id is missing
        """
        if not building_id:
            raise ValueError("Building ID is required.")

        # Validate building ID format (all IDs are "B" + 3 digits, e.g. "B001").
        if not re.match(r'^B\d{3}$', building_id):
            raise ValueError(
                f"Invalid building ID '{building_id}'. "
                f"Building IDs have the format 'B' + 3 digits (e.g. 'B001'). "
                f"Use find_building_id() to look up a building's ID by name."
            )

        # Validate building exists
        node_ids = {node['id'] for node in self._map_data['nodes']}
        if building_id not in node_ids:
            raise ValueError(f"Building '{building_id}' does not exist.")

        for complex_group in self._map_data.get("building_complexes", []):
            if building_id in complex_group.get("member_ids", []):
                return {
                    "is_complex_member": True,
                    "complex_name": complex_group.get('name', 'Unnamed'),
                    "member_ids": complex_group['member_ids'],
                }

        return {"is_complex_member": False, "complex_name": None, "member_ids": []}

    def list_valid_query_properties(self) -> Dict[str, List[str]]:
        """
        List all valid query properties

        Returns:
            Dict with zones, building_types, and amenities lists
        """
        # Extract unique properties from map data
        zones: set[str] = set()
        types: set[str] = set()
        amenities: set[str] = set()

        for node in self._map_data["nodes"]:
            if "zone" in node:
                zones.add(node["zone"])
            if "type" in node:
                types.add(node["type"])
            for floor, items in node.get("internal_amenities", {}).items():
                for item in items:
                    amenities.add(item)

        return {
            "zones": sorted(zones),
            "building_types": sorted(types),
            "amenities": sorted(amenities),
        }


class GeographySystem:
    """
    Agent location tracking and movement system
    Maintains current location state and movement history
    """

    def __init__(self, map_lookup_system: MapLookupSystem):
        """
        Initialize geography system

        Args:
            map_lookup_system: Reference to map lookup system
        """
        self.map_lookup_system = map_lookup_system

        # Initialize at dormitory
        self._state = GeographyState(
            current_location_id="B083",
            current_location_name="Lakeside Dormitory",
            walk_history=[]
        )

    def daily_reset(self) -> None:
        """
        Reset agent location to dormitory at start of new day
        Called by CampusEnvironment during daily_reset
        """
        self._state.current_location_id = "B083"
        self._state.current_location_name = "Lakeside Dormitory"
        self._state.walk_history = []

    def set_location(self, building_id: str) -> str:
        """
        Set agent location (used for source_building_id)
        Called by CampusEnvironment during task initialization

        Args:
            building_id: Building ID to set as current location

        Returns:
            Human-readable success message

        Raises:
            ValueError: If building is not found
        """
        # Get building details to validate and get name
        node = self.map_lookup_system._get_node(building_id)
        building_name = node["name"]
        self._state.current_location_id = building_id
        self._state.current_location_name = building_name

        message = f"You are now located at {building_name}."
        return ensure_english_message(message)

    def walk_to(self, path_info: Dict[str, Any]) -> Dict[str, str]:
        """
        Walk to a location using path information from find_optimal_path

        Args:
            path_info: Path information dictionary with 'path' key

        Returns:
            Dict with name and id of the destination

        Raises:
            ValueError: On invalid path or location mismatch
        """
        # Validate path_info format
        if not isinstance(path_info, dict) or "path" not in path_info:
            raise ValueError("Invalid path_info format. Must be a dictionary with 'path' key.")

        path = path_info["path"]
        if not isinstance(path, list) or len(path) < 2:
            raise ValueError("Invalid path. Must be a list with at least 2 locations.")

        # Validate all building IDs in the path
        node_ids = {node['id'] for node in self.map_lookup_system._map_data['nodes']}
        for bid in path:
            if not re.match(r'^B\d{3}$', bid):
                raise ValueError(
                    f"Invalid building ID '{bid}' in path. "
                    f"Building IDs have the format 'B' + 3 digits (e.g. 'B001'). "
                    f"Use find_building_id() to look up a building's ID by name."
                )
            if bid not in node_ids:
                raise ValueError(
                    f"Building '{bid}' in path does not exist. "
                    f"Use find_optimal_path() to compute a valid path."
                )

        # Validate starting location
        if path[0] != self._state.current_location_id:
            raise ValueError(f"Path starting location '{path[0]}' does not match current location '{self._state.current_location_id}'.")

        # Update location to destination
        destination_id = path[-1]
        node = self.map_lookup_system._get_node(destination_id)
        destination_name = node["name"]

        # Update state
        self._state.current_location_id = destination_id
        self._state.current_location_name = destination_name
        self._state.walk_history.append(path)

        return {"name": destination_name, "id": destination_id}

    def get_current_location(self) -> dict:
        """
        Get current location information

        Returns:
            Dict with "name" and "id" of the current location.
        """
        return {"name": self._state.current_location_name, "id": self._state.current_location_id}

    def get_state_for_evaluation(self) -> GeographyState:
        """
        Get current geography state for evaluation
        Used by CampusTask during evaluation

        Returns:
            Current GeographyState object
        """
        return self._state
