"""
Reservation System for CampusLifeBench
All natural language communications/returns MUST use English only
"""

import random
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..tools import ensure_english_message
from .map_and_geography import MapLookupSystem
from .information import InformationSystem


@dataclass
class ReservationRecord:
    """Represents a reservation record"""
    location_id: str
    area: str
    item_name: str
    seat_id: Optional[str]
    date: str
    time_slot: str
    booking_task_id: str


class ReservationSystem:
    """
    Intelligent reservation system with dynamic availability generation
    Supports both amenity and seat reservations with global state persistence
    """

    def __init__(self, map_lookup_system: MapLookupSystem, information_system: InformationSystem):
        """
        Initialize reservation system

        Args:
            map_lookup_system: Reference to map lookup system for building data
            information_system: Reference to information system for campus data
        """
        self.map_lookup_system = map_lookup_system
        self.information_system = information_system
        self._campus_data = self.information_system.get_campus_data() or {}

        # Global persistent reservations
        self._global_reservations: List[ReservationRecord] = []

        # Current task context (set by CampusTask)
        self._current_task_context: Optional[Dict[str, Any]] = None

        # Configured availability from world_state_change
        self._configured_availability: Dict[str, Any] = {}

    def set_availability(self, parameters: Dict[str, Any]) -> None:
        """
        Set pre-configured availability for a location/item.
        Called by CampusEnvironment based on world_state_change.

        Args:
            parameters: Availability parameters from task data.
        """
        item_name = parameters.get("item_name")
        building_id = parameters.get("building_id")
        available_times = parameters.get("available_times", [])

        if item_name and building_id:
            key = (building_id, item_name)
            self._configured_availability[key] = available_times

    def set_task_context(self, task_data: Dict[str, Any]) -> None:
        """
        Set current task context for intelligent availability generation
        Called by CampusTask before task execution

        Args:
            task_data: Current task data including ground truth and constraints
        """
        self._current_task_context = task_data

    def query_availability(self, building_id: str, date: str) -> dict:
        """
        Query availability for a building on a specific date.

        Returns the names of all bookable amenities at the building
        along with their availability status. Always call this before
        make_booking() to discover valid room names.

        Args:
            building_id: Building ID to query (e.g. "B001")
            date: Date to query, format "Week X, Day" (e.g. "Week 4, Saturday")

        Returns:
            Dict with building_id, building_name, date, and availability info

        Raises:
            ValueError: On invalid input or building not found
        """
        if not all([building_id, date]):
            raise ValueError("Both building_id and date are required.")

        # Validate building_id format (B + 3 digits)
        if not re.match(r'^B\d{3}$', building_id):
            raise ValueError(
                f"Invalid building_id '{building_id}'. "
                f"Must be a building ID in the format 'B' + 3 digits (e.g. 'B001')."
            )

        # Validate date format: "Week X, Day"
        if not re.match(
            r'^Week \d+, (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$',
            date
        ):
            raise ValueError(
                f"Invalid date format '{date}'. "
                f"Expected format: 'Week X, Day' (e.g. 'Week 4, Saturday')."
            )

        # Get building details via _get_node for structured data
        building_data = self.map_lookup_system._get_node(building_id)
        building_name = building_data.get("name", building_id)

        # Decide generation strategy based on ground_truth
        availability = {}
        use_deterministic_seats = False
        if self._current_task_context:
            ground_truth = self._current_task_context.get("ground_truth", {})
            if isinstance(ground_truth, dict) and "seat_id" in ground_truth:
                use_deterministic_seats = True

        if use_deterministic_seats:
            # For seat-specific tasks, generate a detailed puzzle
            availability = self._generate_deterministic_availability(building_data, date)
        else:
            # For all other tasks, generate random hierarchical availability
            availability = self._generate_random_hierarchical_availability(building_data, date)

        return availability

    def _is_target_location(self, location_id: str, date: str, building_data: Optional[Dict[str, Any]]) -> bool:
        """
        Check if this is the target location for current task

        Args:
            location_id: Building ID to check
            date: Date to check
            building_data: Pre-fetched building data dictionary

        Returns:
            True if this is the target location and date
        """
        if not self._current_task_context or not isinstance(building_data, dict):
            return False

        details = self._current_task_context.get("details", {})
        target_library = details.get("target_library")
        target_date = self._current_task_context.get("target_date")

        # Check if location matches target
        if target_library:
            building_name = building_data.get("name")
            if building_name == target_library and date == target_date:
                return True

        return False

    def _generate_deterministic_availability(self, building_data: Dict[str, Any], date: str) -> Dict[str, Dict[str, Any]]:
        """
        Generate availability for a seat-specific task using real data from campus_data.json,
        with intelligent distractor generation.

        Args:
            building_data: Building information (used to get the building ID)
            date: Date for availability

        Returns:
            Hierarchical availability dictionary with real seat data and distractors.
        """
        if not self._current_task_context:
            return {}

        availability = {}
        details = self._current_task_context.get("details", {})
        ground_truth = self._current_task_context.get("ground_truth", {})

        # 1. Get task parameters
        location_id = building_data.get("id")
        if not location_id:
            return {}

        target_item_name = ground_truth.get("item_name", "Study Area")
        required_features = set(details.get("implied_requirements", []))
        task_time = details.get("task_time", "16:30")
        duration_hours = details.get("reservation_duration_hours", 1.5)
        target_time_slot = self._calculate_time_slot(task_time, duration_hours)

        # 2. Find the correct building and room to extract all real seats
        all_real_seats_in_room = []
        detailed_building_data = next((lib for lib in self._campus_data.get("library_seats", {}).get("libraries", []) if lib.get("id") == location_id), None)

        if not detailed_building_data:
            return self._generate_fallback_availability(target_time_slot, target_item_name)

        # Find the specific room in the detailed data
        target_room_data = None
        for floor, rooms in detailed_building_data.get("internal_amenities", {}).items():
            for room in rooms:
                if isinstance(room, dict) and room.get("room_name") == target_item_name:
                    target_room_data = room
                    break
            if target_room_data:
                break

        if target_room_data:
            all_real_seats_in_room.extend(target_room_data.get("seats", []))

        if not all_real_seats_in_room:
            return self._generate_fallback_availability(target_time_slot, target_item_name)

        # 3. Separate seats into correct and distractor piles
        correct_seats = []
        distractor_seats = []
        for seat in all_real_seats_in_room:
            seat_features = set(seat.get("features", []))
            if required_features.issubset(seat_features):
                correct_seats.append(seat)
            else:
                distractor_seats.append(seat)

        # 4. Build the availability for the target time slot
        seats_for_target_slot = correct_seats.copy()
        # Add a number of distractors to meet the desired count, up to a max of 10 total seats
        num_distractors_to_add = min(len(distractor_seats), 10 - len(seats_for_target_slot))
        if num_distractors_to_add > 0:
            seats_for_target_slot.extend(random.sample(distractor_seats, k=num_distractors_to_add))

        random.shuffle(seats_for_target_slot)
        # Wrap in floor key for consistency with hierarchical mode
        target_floor = "floor_1"
        if target_room_data:
            # Find the actual floor from detailed data
            for fl, rooms in detailed_building_data.get("internal_amenities", {}).items():
                for room in rooms:
                    if isinstance(room, dict) and room.get("room_name") == target_item_name:
                        target_floor = fl
                        break
        availability[target_time_slot] = {
            target_floor: {target_item_name: {"seats": seats_for_target_slot}}
        }

        # 5. Generate availability for other time slots using only distractors or a subset of real seats
        other_slots = ["09:00-10:30", "10:30-12:00", "14:00-15:30"]
        if target_time_slot in other_slots:
            other_slots.remove(target_time_slot)

        for slot in other_slots:
            num_other_seats = min(len(all_real_seats_in_room), 5)
            other_seats_sample = random.sample(all_real_seats_in_room, k=num_other_seats)
            availability[slot] = {
                target_floor: {target_item_name: {"seats": other_seats_sample}}
            }

        return availability

    def _generate_fallback_availability(self, time_slot: str, item_name: str) -> Dict[str, Any]:
        """Generates minimal fallback availability when real data isn't found."""
        return {
            time_slot: {
                item_name: {"seats": []}
            }
        }

    def _generate_random_hierarchical_availability(self, building_data: Dict[str, Any], date: str) -> Dict[str, Dict[str, Any]]:
        """
        Generate hierarchical availability using real data for non-seat-specific tasks.
        Args:
            building_data: Building information
            date: Date for availability
        Returns:
            Hierarchical availability dictionary
        """
        availability = {}
        time_slots = ["09:00-10:30", "10:30-12:00", "14:00-15:30", "15:30-17:00", "16:30-18:00"]

        # Include all GT time slots so the correct answers are always available.
        # GT may have: top-level time_slot, reservation_made.time_slot, or
        # reservation_made_1/2/3.time_slot for multi-reservation tasks.
        if self._current_task_context:
            gt = self._current_task_context.get("ground_truth", {})
            if isinstance(gt, dict):
                for gk, gv in gt.items():
                    slot = None
                    if gk == "time_slot":
                        slot = gv
                    elif isinstance(gv, dict):
                        slot = gv.get("time_slot")
                    if slot and slot not in time_slots:
                        time_slots.append(slot)

        # 1. Get building amenities from the primary building_data which is from map_v1.5.json
        amenities_from_map = building_data.get("internal_amenities", {})
        if not amenities_from_map or not isinstance(amenities_from_map, dict):
            return {}

        # 2. Find the corresponding detailed building data from campus_data
        location_id = building_data.get("id")
        detailed_building_data = next((lib for lib in self._campus_data.get("library_seats", {}).get("libraries", []) if lib.get("id") == location_id), None)

        # detailed_building_data may be None for non-library buildings — that's
        # fine; amenities without detailed seat info get {"status": "available"}.

        # 3. Create a lookup for detailed room info
        room_details_lookup = {}
        for floor, rooms in (detailed_building_data or {}).get("internal_amenities", {}).items():
            for room in rooms:
                if isinstance(room, dict) and "room_name" in room:
                    room_details_lookup[room["room_name"]] = room

        # 4. Generate availability for each time slot based on map structure
        for slot in time_slots:
            availability[slot] = {}
            # Iterate through floors and rooms from the map data
            for floor, room_names in amenities_from_map.items():
                floor_amenities = {}
                for room_name in room_names:
                    # Look up detailed info in campus_data.
                    # Map names may have a suffix (e.g. "Lecture Hall (101)")
                    # while campus_data uses the base name ("Lecture Hall").
                    detailed_room = room_details_lookup.get(room_name)
                    if not detailed_room:
                        for base_name, room_data in room_details_lookup.items():
                            if room_name.startswith(base_name + " ("):
                                detailed_room = room_data
                                break

                    if detailed_room:
                        seats = detailed_room.get("seats", [])
                        floor_amenities[room_name] = {
                            "seats": seats,
                            "features": detailed_room.get("features", [])
                        }
                    else:
                        # If no detailed info, mark as available without seats
                        floor_amenities[room_name] = {"status": "available"}

                if floor_amenities:
                    if floor not in availability[slot]:
                        availability[slot][floor] = {}
                    availability[slot][floor].update(floor_amenities)

        return availability

    def _calculate_time_slot(self, start_time: str, duration_hours: float) -> str:
        """
        Calculate time slot from start time and duration

        Args:
            start_time: Start time (e.g., "16:30")
            duration_hours: Duration in hours

        Returns:
            Time slot string (e.g., "16:30-18:00")
        """
        try:
            hour, minute = map(int, start_time.split(":"))
            start_minutes = hour * 60 + minute
            end_minutes = start_minutes + int(duration_hours * 60)

            end_hour = end_minutes // 60
            end_minute = end_minutes % 60

            return f"{start_time}-{end_hour:02d}:{end_minute:02d}"
        except:
            return f"{start_time}-{start_time}"  # Fallback

    def make_booking(self, building_id: str, item_name: str, date: str, time_slot: str, seat_id: Optional[str] = None) -> None:
        """
        Make a booking for a building/seat.

        The item_name must exactly match an amenity name at the building.
        Call query_availability(building_id, date) first to discover valid
        names; an invalid name raises ValueError.

        Args:
            building_id: Building ID (e.g. "B001")
            item_name: Exact name of the room or area to book (e.g. "Group
                Study Room 201", "Study Area"). Must match a room at the
                building — use query_availability() to discover valid names.
            date: Date for booking, format "Week X, Day" (e.g. "Week 4, Saturday")
            time_slot: Time slot to book (e.g. "14:00-16:00")
            seat_id: Optional specific seat ID (e.g. "B001-F01-S001") for seat bookings

        Returns:
            None. Raises ValueError on failure.

        Raises:
            ValueError: On missing inputs, invalid room name, or booking conflict
        """
        if not all([building_id, item_name, date, time_slot]):
            raise ValueError("building ID, amenity, date, and time slot are all required.")

        # Validate building_id format (B + 3 digits)
        if not re.match(r'^B\d{3}$', building_id):
            raise ValueError(
                f"Invalid building_id '{building_id}'. "
                f"Must be a building ID in the format 'B' + 3 digits (e.g. 'B001')."
            )

        # Validate date format: "Week X, Day"
        if not re.match(r'^Week \d+, (Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$', date):
            raise ValueError(
                f"Invalid date format '{date}'. "
                f"Expected format: 'Week X, Day' (e.g. 'Week 4, Saturday')."
            )

        # Validate time_slot format: "HH:MM-HH:MM"
        if not re.match(r'^\d{2}:\d{2}-\d{2}:\d{2}$', time_slot):
            raise ValueError(
                f"Invalid time_slot format '{time_slot}'. "
                f"Expected format: 'HH:MM-HH:MM' (e.g. '14:00-16:00')."
            )

        # Validate that the building exists
        building_data = self.map_lookup_system._get_node(building_id)

        # Validate item_name against the building's actual bookable items.
        # The map data stores room names with suffixes like "(101)" or "(B11)";
        # accept if item_name matches the start of any room name.
        internal_amenities = building_data.get("internal_amenities", {})
        all_room_names = []
        for floor_rooms in internal_amenities.values():
            if isinstance(floor_rooms, list):
                all_room_names.extend(floor_rooms)
        # Amenity-existence check is unconditional: when a building lists no amenities at all, booking a
        # bogus one used to fall through and silently create a reservation, so raise instead.
        if not all_room_names:
            building_name = building_data.get("name", building_id)
            raise ValueError(
                f"{building_name} ({building_id}) has no bookable amenities. "
                f"Use query_availability({building_id!r}, <date>) to find bookable amenities."
            )
        match = any(
            room_name == item_name or room_name.startswith(item_name + " (")
            for room_name in all_room_names
        )
        if not match:
            building_name = building_data.get("name", building_id)
            raise ValueError(
                f"'{item_name}' is not a bookable amenity at {building_name} ({building_id}). "
                f"Available amenities: {all_room_names}. "
                f"Use query_availability({building_id!r}, <date>) to see what's available."
            )

        # Validate seat_id against amenity seat data
        detailed_building = next(
            (lib for lib in self._campus_data.get("library_seats", {}).get("libraries", [])
             if lib.get("id") == building_id), None
        )
        amenity_seat_ids = set()
        if detailed_building:
            for floor, rooms in detailed_building.get("internal_amenities", {}).items():
                for room in rooms:
                    if isinstance(room, dict) and (
                        room.get("room_name") == item_name
                        or room.get("room_name", "").startswith(item_name + " (")
                        or item_name.startswith(room.get("room_name", "") + " (")
                    ):
                        for seat in room.get("seats", []):
                            amenity_seat_ids.add(seat["seat_id"])

        if seat_id:
            if not seat_id.startswith(building_id + "-"):
                raise ValueError(
                    f"Invalid seat_id '{seat_id}': must start with building ID '{building_id}-'."
                )
            if not detailed_building:
                raise ValueError(
                    f"Building '{building_id}' does not have bookable seats. "
                    f"Do not pass seat_id when booking at this building."
                )
            if not amenity_seat_ids:
                raise ValueError(
                    f"Amenity '{item_name}' at {building_data.get('name', building_id)} does not have individual seats. "
                    f"Book without seat_id, or choose a different amenity."
                )
            if seat_id not in amenity_seat_ids:
                raise ValueError(
                    f"Seat '{seat_id}' does not exist in '{item_name}' at {building_data.get('name', building_id)}. "
                    f"Use query_availability({building_id!r}, <date>) to see available seats."
                )
        elif amenity_seat_ids:
            raise ValueError(
                f"Amenity '{item_name}' at {building_data.get('name', building_id)} has individual seats. "
                f"You must specify a seat_id. "
                f"Use query_availability({building_id!r}, <date>) to see available seats and their features."
            )

        # Check for conflicts with existing reservations
        for reservation in self._global_reservations:
            if (reservation.location_id == building_id and
                    reservation.date == date and
                    self._time_slots_overlap(reservation.time_slot, time_slot)):

                if ((seat_id and reservation.seat_id == seat_id) or
                        (not seat_id and reservation.item_name == item_name)):
                    raise ValueError(f"The requested amenity '{item_name}' is already booked for the specified time slot.")

        # Create reservation record
        task_id = self._current_task_context.get("task_id", "unknown") if self._current_task_context else "unknown"

        reservation = ReservationRecord(
            location_id=building_id,
            area="floor_1",  # Default area
            item_name=item_name,
            seat_id=seat_id,
            date=date,
            time_slot=time_slot,
            booking_task_id=task_id
        )

        # Add to global reservations
        self._global_reservations.append(reservation)

        return None

    def _time_slots_overlap(self, slot1: str, slot2: str) -> bool:
        """
        Check if two time slots overlap

        Args:
            slot1: First time slot (e.g., "14:00-16:00")
            slot2: Second time slot

        Returns:
            True if slots overlap
        """
        try:
            def parse_time_slot(slot):
                start_str, end_str = slot.split("-")
                start_hour, start_min = map(int, start_str.split(":"))
                end_hour, end_min = map(int, end_str.split(":"))
                return start_hour * 60 + start_min, end_hour * 60 + end_min

            start1, end1 = parse_time_slot(slot1)
            start2, end2 = parse_time_slot(slot2)

            return not (end1 <= start2 or end2 <= start1)
        except:
            return False  # If parsing fails, assume no overlap

    def get_reservations_for_evaluation(self, task_id: str) -> List[ReservationRecord]:
        """
        Get reservations made by a specific task for evaluation
        Used by CampusTask during evaluation

        Args:
            task_id: Task ID to filter by

        Returns:
            List of ReservationRecord objects for the task
        """
        return [r for r in self._global_reservations if r.booking_task_id == task_id]

    def get_all_reservations(self) -> List[ReservationRecord]:
        """
        Get all reservations for debugging/testing

        Returns:
            List of all ReservationRecord objects
        """
        return self._global_reservations.copy()
