"""
CampusEnvironment - Core environment class for CampusLifeBench
All natural language communications/returns MUST use English only
"""

import os
import json
from typing import Dict, Any, Optional, List
from pathlib import Path

from .tools import ToolResult, ensure_english_message
from .systems import (
    WorldTimeSystem, CalendarSystem, MapLookupSystem, GeographySystem,
    ReservationSystem, InformationSystem, CourseSelectionSystem, EmailSystem
)


class CampusEnvironment:
    """
    Core environment class that maintains all campus simulation state
    and provides unified tool interface for Agent interaction.

    This class serves as the single source of truth for all campus state
    and delegates tool calls to appropriate subsystems.
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the campus environment with all subsystems

        Args:
            data_dir: Directory containing campus data files
        """
        # Set up data directory
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        self.data_dir = Path(data_dir)

        # Check for background directory structure
        self.background_dir = self.data_dir / "background"
        if not self.background_dir.exists():
            # Fallback to data_dir for backward compatibility
            self.background_dir = self.data_dir
            print(f"⚠️  Background directory not found, using fallback: {self.background_dir}")
        else:
            print(f"✅ Using background directory: {self.background_dir}")

        # Initialize all subsystems
        self._initialize_subsystems()

        # Track current day for daily reset functionality
        self._current_day: Optional[str] = None

    def _initialize_subsystems(self):
        """Initialize all campus subsystems"""
        # World Time System (no tools, logic handled by CampusTask)
        self.world_time_system = WorldTimeSystem()

        # Calendar System
        self.calendar_system = CalendarSystem()

        # Map and Geography Systems
        map_data_path = self.background_dir / "map_v1.5.json"
        self.map_lookup_system = MapLookupSystem(map_data_path)
        self.geography_system = GeographySystem(self.map_lookup_system)

        # Information System - use background directory
        bibliography_path = self.background_dir / "bibliography.json"
        data_system_path = self.background_dir / "campus_data.json"
        self.information_system = InformationSystem(bibliography_path, data_system_path)

        # Reservation System
        self.reservation_system = ReservationSystem(
            map_lookup_system=self.map_lookup_system,
            information_system=self.information_system
        )

        # Course Selection System
        courses_path = self.background_dir / "courses.json"
        self.course_selection_system = CourseSelectionSystem(courses_path)

        # Email System
        self.email_system = EmailSystem()

    @staticmethod
    def _wrap(fn, *args, **kwargs) -> ToolResult:
        """
        Wrap a subsystem method call into a ToolResult.

        Calls fn(*args, **kwargs) and:
        - Returns ToolResult.success(result) on success
        - Returns ToolResult.failure(str(e)) for ValueError
        - Returns ToolResult.error(str(e)) for any other exception
        """
        try:
            return ToolResult.success(fn(*args, **kwargs))
        except ValueError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            return ToolResult.error(str(e))

    def daily_reset(self, new_day: str) -> None:
        """
        Perform daily reset operations
        Called by CampusTask when a new simulation day begins

        Args:
            new_day: The new simulation day (e.g., "Week 2, Saturday")
        """
        self._current_day = new_day

        # Reset geography to dormitory
        self.geography_system.daily_reset()

        # Other systems may need daily reset in the future
        # self.calendar_system.daily_reset()
        # self.reservation_system.daily_reset()

    def set_initial_location(self, building_id: str) -> ToolResult:
        """
        Set agent's initial location for a task
        Called by CampusTask when source_building_id is specified

        Args:
            building_id: The building ID to set as current location

        Returns:
            ToolResult indicating success or failure
        """
        return self._wrap(self.geography_system.set_location, building_id)

    def get_current_location_for_validation(self) -> str:
        """
        Get current location ID for require_place validation
        Used by CampusTask for prerequisite checking

        Returns:
            Current building ID
        """
        # TODO: Get get_current_location() to return structured data so that we don't have to access private _state
        return self.geography_system._state.current_location_id

    def apply_world_state_changes(self, changes: List[Dict[str, Any]]) -> None:
        """
        Apply world state changes before task execution
        Called by CampusTask during _reset

        Args:
            changes: List of world state change objects
        """
        # Reset semester to default before applying changes for a new task
        self.course_selection_system.set_current_semester("Semester 1")

        for change in changes:
            change_type = change.get("change_type")
            system = change.get("system")
            action = change.get("action")

            if change_type == "popularity_update":
                course_code = change.get("course_code")
                new_value = change.get("new_value")
                self.course_selection_system.update_course_popularity(course_code, new_value)
                # If a specific course code for semester 2 is updated, set the semester
                if course_code == "COMS00311213":
                    self.course_selection_system.set_current_semester("Semester 2")

            elif change_type == "seats_left_update":
                course_code = change.get("course_code")
                new_value = change.get("new_value")
                self.course_selection_system.update_course_seats(course_code, new_value)

            elif change_type == "advisor_availability_set":
                advisor_id = change.get("advisor_id")
                date = change.get("date")
                available_slots = change.get("available_slots", [])
                if advisor_id and date and available_slots:
                    self.calendar_system.set_advisor_availability(advisor_id, date, available_slots)

            elif system == "reservation" and action == "set_availability":
                parameters = change.get("parameters", {})
                if parameters:
                    self.reservation_system.set_availability(parameters)

    # ========== Calendar System Tools ==========

    def add_event(self, calendar_id: str, event_title: str, location: str, time: str, description: Optional[str] = None) -> ToolResult:
        """Add an event to the specified calendar"""
        return self._wrap(self.calendar_system.add_event, calendar_id, event_title, location, time, description)

    def remove_event(self, calendar_id: str, event_id: str) -> ToolResult:
        """Remove an event from the specified calendar"""
        return self._wrap(self.calendar_system.remove_event, calendar_id, event_id)

    def update_event(self, calendar_id: str, event_id: str, new_details: Dict[str, Any]) -> ToolResult:
        """Update an event in the specified calendar"""
        return self._wrap(self.calendar_system.update_event, calendar_id, event_id, new_details)

    def view_schedule(self, calendar_id: str, date: str) -> ToolResult:
        """View schedule for the specified calendar and date"""
        return self._wrap(self.calendar_system.view_schedule, calendar_id, date)

    def query_advisor_availability(self, advisor_id: str, date: str) -> ToolResult:
        """Query advisor availability for the specified date"""
        return self._wrap(self.calendar_system.query_advisor_availability, advisor_id, date)

    # ========== Map Lookup System Tools ==========

    def find_building_id(self, building_name: str) -> ToolResult:
        """Find building ID by name or alias"""
        try:
            result = self.map_lookup_system.find_building_id(building_name)
            message = f"Found building '{result['name']}' with ID '{result['id']}'."
            return ToolResult.success(message, result)
        except ValueError as e:
            return ToolResult.failure(str(e))

    def get_building_details(self, building_id: str) -> ToolResult:
        """Get detailed information about a building"""
        return self._wrap(self.map_lookup_system.get_building_details, building_id)

    def find_room_location(self, room_query: str, building_id: Optional[str] = None, zone: Optional[str] = None) -> ToolResult:
        """Find room location within campus or specified area"""
        return self._wrap(self.map_lookup_system.find_room_location, room_query, building_id, zone)

    def find_optimal_path(self, source_building_id: str, target_building_id: str, constraints: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Find optimal path between two buildings"""
        try:
            result = self.map_lookup_system.find_optimal_path(source_building_id, target_building_id, constraints)
            message = f"Optimal path found: {' -> '.join(result['path_names'])}."
            return ToolResult.success(message, result)
        except ValueError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            return ToolResult.error(str(e))

    def query_buildings_by_property(self, zone: Optional[str] = None, building_type: Optional[str] = None, amenity: Optional[str] = None) -> ToolResult:
        """Query buildings by properties"""
        return self._wrap(self.map_lookup_system.query_buildings_by_property, zone, building_type, amenity)

    def get_building_complex_info(self, building_id: str) -> ToolResult:
        """Get building complex information"""
        return self._wrap(self.map_lookup_system.get_building_complex_info, building_id)

    def list_valid_query_properties(self) -> ToolResult:
        """List all valid query properties"""
        return self._wrap(self.map_lookup_system.list_valid_query_properties)

    # ========== Geography System Tools ==========

    def walk_to(self, path_info: Dict[str, Any]) -> ToolResult:
        """Walk to a location using path information"""
        return self._wrap(self.geography_system.walk_to, path_info)

    def get_current_location(self) -> ToolResult:
        """Get current location"""
        return self._wrap(self.geography_system.get_current_location)

    # ========== Reservation System Tools ==========

    def query_availability(self, location_id: str, date: str) -> ToolResult:
        """Query availability for a location on a specific date"""
        return self._wrap(self.reservation_system.query_availability, location_id, date)

    def make_booking(self, location_id: str, item_name: str, date: str, time_slot: str, seat_id: Optional[str] = None) -> ToolResult:
        """Make a booking for a location/seat"""
        return self._wrap(self.reservation_system.make_booking, location_id, item_name, date, time_slot, seat_id)

    # ========== Information System Tools ==========

    def list_chapters(self, book_title: str) -> ToolResult:
        """List chapters in a book"""
        return self._wrap(self.information_system.list_chapters, book_title)

    def list_sections(self, book_title: str, chapter_title: str) -> ToolResult:
        """List sections in a chapter"""
        return self._wrap(self.information_system.list_sections, book_title, chapter_title)

    def list_articles(self, book_title: str, chapter_title: str, section_title: str) -> ToolResult:
        """List articles in a section"""
        return self._wrap(self.information_system.list_articles, book_title, chapter_title, section_title)

    def view_article(self, identifier: str, by: str) -> ToolResult:
        """View an article by title or ID"""
        return self._wrap(self.information_system.view_article, identifier, by)

    def list_by_category(self, category: str, entity_type: str, level: Optional[str] = None) -> ToolResult:
        """List entities by category"""
        return self._wrap(self.information_system.list_by_category, category, entity_type, level)

    def query_by_identifier(self, identifier: str, by: str, entity_type: str) -> ToolResult:
        """Query entity by identifier"""
        return self._wrap(self.information_system.query_by_identifier, identifier, by, entity_type)

    def list_books_by_category(self, category: str) -> ToolResult:
        """List library books by category"""
        return self._wrap(self.information_system.list_books_by_category, category)

    def search_books(self, query: str, search_type: str = "title") -> ToolResult:
        """Search library books by title or author"""
        return self._wrap(self.information_system.search_books, query, search_type)

    # ========== Course Selection System Tools ==========

    def browse_courses(self, filters: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Browse available courses with optional filters"""
        try:
            courses = self.course_selection_system.browse_courses(filters)
            message = f"Found {len(courses)} course(s):"
            for c in courses:
                sched = c.get("schedule", {})
                days = ", ".join(sched.get("days", []))
                message += f"\n- {c['section_id']}: {c['course_name']}"
                message += f" (Credits: {c.get('credits', 'N/A')}, Popularity: {c.get('popularity', 'N/A')})"
                message += f"\n  Instructor: {c.get('instructor', 'N/A')}"
                message += f"\n  Schedule: {days}, {sched.get('time', 'N/A')}"
                message += f"\n  Location: {sched.get('location', 'N/A')}"
            return ToolResult.success(message, data={"courses": courses})
        except ValueError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            return ToolResult.error(str(e))

    def add_course(self, section_id: str) -> ToolResult:
        """Add a course to draft schedule"""
        return self._wrap(self.course_selection_system.add_course, section_id)

    def remove_course(self, section_id: str) -> ToolResult:
        """Remove a course from draft schedule"""
        return self._wrap(self.course_selection_system.remove_course, section_id)

    def assign_pass(self, section_id: str, pass_type: str) -> ToolResult:
        """Assign a pass type to a course"""
        return self._wrap(self.course_selection_system.assign_pass, section_id, pass_type)

    def view_draft(self) -> ToolResult:
        """View current draft schedule"""
        return self._wrap(self.course_selection_system.view_draft)

    def submit_draft(self) -> ToolResult:
        """Submit draft schedule for final registration"""
        return self._wrap(self.course_selection_system.submit_draft)

    # ========== Email System Tools ==========

    def send_email(self, recipient: str, subject: str, body: str) -> ToolResult:
        """Send an email"""
        return self._wrap(self.email_system.send_email, recipient, subject, body)

    def get_and_clear_self_schedule_changes(self) -> List[Dict[str, Any]]:
        """Get calendar changes and clear the log"""
        return self.calendar_system.get_and_clear_self_schedule_changes()

    # =========================================================================
    # Raw (unwrapped) tool methods — return str, raise ValueError on error.
    # Used by the JAZ integration (stulife_env.py) so agents receive plain
    # strings instead of ToolResult objects.
    # =========================================================================

    # Calendar
    def raw_add_event(self, calendar_id: str, event_title: str, location: str, time: str, description: Optional[str] = None) -> str:
        """Add an event to a calendar.

        Args:
            calendar_id: Use "self" for your personal calendar. For advisor or club calendars,
                use their email address (e.g. "william.davis@example.com" or "art_club@example.com").
            event_title: Title of the event.
            location: Location of the event.
            time: Time of the event, format "Week X, Day, HH:MM-HH:MM"
                (e.g. "Week 3, Monday, 15:00-16:00").
            description: Optional detailed description.

        Returns:
            Human-readable result string.
        """
        return self.calendar_system.add_event(calendar_id, event_title, location, time, description)

    def raw_remove_event(self, calendar_id: str, event_id: str) -> str:
        """Remove an event from a calendar.

        Args:
            calendar_id: Calendar identifier (e.g. "self").
            event_id: ID of the event to remove.

        Returns:
            Human-readable result string.
        """
        return self.calendar_system.remove_event(calendar_id, event_id)

    def raw_update_event(self, calendar_id: str, event_id: str, new_details: Dict[str, Any]) -> str:
        """Update an existing calendar event.

        Args:
            calendar_id: Calendar identifier (e.g. "self").
            event_id: ID of the event to update.
            new_details: Dict of fields to update, e.g. {"location": "New Room", "time": "Week 3, Monday, 16:00-17:00"}.

        Returns:
            Human-readable result string.
        """
        return self.calendar_system.update_event(calendar_id, event_id, new_details)

    def raw_view_schedule(self, calendar_id: str, date: str) -> str:
        """View all events on a specific date for a calendar.

        Args:
            calendar_id: Calendar identifier (e.g. "self", or an advisor/club email).
            date: Date to view, format "Week X, Day" (e.g. "Week 3, Monday").

        Returns:
            Human-readable result string.
        """
        return self.calendar_system.view_schedule(calendar_id, date)

    def raw_query_advisor_availability(self, advisor_id: str, date: str) -> str:
        """Check an advisor's available time slots on a given date.

        Args:
            advisor_id: Advisor identifier (e.g. "T0001").
            date: Date to query, format "Week X, Day" (e.g. "Week 4, Tuesday").

        Returns:
            Human-readable result string.
        """
        return self.calendar_system.query_advisor_availability(advisor_id, date)

    # Map lookup
    def raw_find_building_id(self, building_name: str) -> Dict[str, str]:
        """Find a building's unique ID by its name or alias.

        Args:
            building_name: Name or alias of the building (e.g. "Grand Central Library").

        Returns:
            Dict with "name" and "id" keys.
        """
        # DIFF from original: returns Dict instead of str so the agent can do
        # ``bid = campus.find_building_id("...")["id"]`` without parsing.
        return self.map_lookup_system.find_building_id(building_name)

    def raw_get_building_details(self, building_id: str) -> str:
        """Get all details for a building (name, zone, type, amenities, rooms).

        Args:
            building_id: Building ID (e.g. "B001").

        Returns:
            Human-readable result string.
        """
        return self.map_lookup_system.get_building_details(building_id)

    def raw_find_room_location(self, room_query: str, building_id: Optional[str] = None, zone: Optional[str] = None) -> str:
        """Find the location of a specific room by name or number.

        Args:
            room_query: Name or number of the room (e.g. "Seminar Room 101").
            building_id: Optional building ID to narrow the search.
            zone: Optional zone name to narrow the search.

        Returns:
            Human-readable result string.
        """
        return self.map_lookup_system.find_room_location(room_query, building_id, zone)

    def raw_find_optimal_path(self, source_building_id: str, target_building_id: str, constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Find the best path between two buildings.

        Returns a dict that can be passed directly to walk_to(), e.g.::

            path = campus.find_optimal_path("B010", "B127")
            campus.walk_to(path)

        Use find_building_id to resolve building names to IDs if needed.

        Args:
            source_building_id: Starting building ID.
            target_building_id: Destination building ID.
            constraints: Optional dict of path property preferences. Keys must match
                edge property names and values must match exactly (edges that don't
                match get a cost penalty, so the path prefers matching edges but may
                still use non-matching ones if no alternative exists). Valid keys and
                their possible values:
                - "path_type": "Indoor" | "Outdoor"
                - "rain_exposure": "Covered" | "Exposed" | "Exposed_Puddles" | "Exposed_Slippery"
                - "illumination": "Good" | "Poor"
                - "accessibility": "Wheelchair" | "Standard" | "Stairs_Only" | "Steep_Grade" | "Uneven_Surface" | "No_Bicycle"
                - "congestion": "Low" | "Normal" | "High_During_Class_Change" | "High_After_Classes"
                Example: {"path_type": "Indoor", "rain_exposure": "Covered", "illumination": "Good"}

        Returns:
            Dict with "path" (list of building IDs) and "path_names" (list of building names).
            Pass this directly to walk_to().
        """
        # DIFF from original: returns Dict instead of str.
        # Original: returned a human-readable string
        # ``f"Optimal path found: {' -> '.join(result['path_names'])}."``
        # which discarded the structured path data (building IDs).
        # Issue: the agent needs the building ID list to pass to walk_to(), but had
        # to parse it from a human-readable string, often getting it wrong (e.g.
        # passing just waypoint IDs instead of the full path with intermediates).
        # Fix: return the raw dict so the agent can do
        # ``path = campus.find_optimal_path(...); campus.walk_to(path)``.

        return self.map_lookup_system.find_optimal_path(source_building_id, target_building_id, constraints)

    def raw_query_buildings_by_property(self, zone: Optional[str] = None, building_type: Optional[str] = None, amenity: Optional[str] = None) -> str:
        """Query buildings based on properties. At least one filter is required.

        Args:
            zone: Zone name to filter by.
            building_type: Building type to filter by.
            amenity: Amenity to filter by (e.g. "Coffee Shop").

        Returns:
            Human-readable result string.
        """
        return self.map_lookup_system.query_buildings_by_property(zone, building_type, amenity)

    def raw_get_building_complex_info(self, building_id: str) -> str:
        """Get complex/cluster membership info for a building.

        Args:
            building_id: Building ID to look up.

        Returns:
            Human-readable result string.
        """
        return self.map_lookup_system.get_building_complex_info(building_id)

    def raw_list_valid_query_properties(self) -> str:
        """List all valid values for zone, building_type, and amenity filters.

        Returns:
            Human-readable result string.
        """
        return self.map_lookup_system.list_valid_query_properties()

    # Geography
    def raw_walk_to(self, path_info: Dict[str, Any]) -> Dict[str, str]:
        """Move to a location by following a path of building IDs.

        Typical usage: call find_optimal_path to get the route, then pass it::

            path = campus.find_optimal_path("B083", "B001")
            campus.walk_to(path)

        Args:
            path_info: Dict with a "path" key containing an ordered list of building IDs
                from current location to destination (at least 2 entries).

        Returns:
            Dict with "name" and "id" of the new location.
        """
        # DIFF from original: returns Dict instead of str.
        # Original: returned ``"Successfully walked to X. You are now at X."``
        # Issue: agent needs the new location ID for subsequent operations.
        # Fix: return {"name": ..., "id": ...} of the new location.

        self.geography_system.walk_to(path_info)
        state = self.geography_system._state
        return {"name": state.current_location_name, "id": state.current_location_id}

    def raw_get_current_location(self) -> Dict[str, str]:
        """Get your current building location.

        Returns:
            Dict with "name" and "id" keys.
        """
        # DIFF from original: returns Dict instead of str.
        # Original: returned ``"You are currently at X (ID: B001)."``
        # Issue: the agent needs the ID to pass to find_optimal_path, etc.
        # Fix: return {"name": ..., "id": ...}.

        state = self.geography_system._state
        return {"name": state.current_location_name, "id": state.current_location_id}

    # Reservation
    def raw_query_availability(self, location_id: str, date: str) -> str:
        """Query availability of bookable spaces (rooms, seats) at a location.

        Args:
            location_id: Building ID (e.g. "B001").
            date: Date to query, format "Week X, Day" (e.g. "Week 4, Saturday").

        Returns:
            Human-readable result string.
        """
        return self.reservation_system.query_availability(location_id, date)

    def raw_make_booking(self, location_id: str, item_name: str, date: str, time_slot: str, seat_id: Optional[str] = None) -> str:
        """Book a specific room or seat at a location.

        Args:
            location_id: Building ID.
            item_name: Name of the room or area (e.g. "Group Study Room 201", "Study Area").
            date: Date for the booking, format "Week X, Day".
            time_slot: Time slot to book (e.g. "14:00-16:00").
            seat_id: Optional specific seat ID (e.g. "B001-F01-S001") when booking a seat.

        Returns:
            Human-readable result string.
        """
        return self.reservation_system.make_booking(location_id, item_name, date, time_slot, seat_id)

    # Information / bibliography
    def raw_list_chapters(self, book_title: str) -> str:
        """List all chapters in a textbook or handbook.

        Use this for querying assigned textbooks and handbooks only.
        To search the main library collection, use search_books or list_books_by_category.

        Available handbooks: "Student Handbook", "Academic Integrity Guidelines",
            "Academic Programs Guide".
        Available textbooks: "A Panorama of Computing: From Bits to Artificial Intelligence",
            "Linear Algebra and Its Applications", "Mathematical Analysis",
            "Military Theory and National Defense", "Programming for Everyone",
            "Innovation and Entrepreneurship", "Mental Health and Wellness",
            "Advanced Programming Concepts".

        Args:
            book_title: Exact title of the book.

        Returns:
            Human-readable result string.
        """
        return self.information_system.list_chapters(book_title)

    def raw_list_sections(self, book_title: str, chapter_title: str) -> str:
        """List all sections in a chapter of a textbook or handbook.

        Args:
            book_title: Exact title of the book.
            chapter_title: Exact title of the chapter.

        Returns:
            Human-readable result string.
        """
        return self.information_system.list_sections(book_title, chapter_title)

    def raw_list_articles(self, book_title: str, chapter_title: str, section_title: str) -> str:
        """List all articles in a section of a textbook or handbook.

        Args:
            book_title: Exact title of the book.
            chapter_title: Exact title of the chapter.
            section_title: Exact title of the section.

        Returns:
            Human-readable result string.
        """
        return self.information_system.list_articles(book_title, chapter_title, section_title)

    def raw_view_article(self, identifier: str, by: str) -> str:
        """View the full content of an article from a textbook or handbook.

        Args:
            identifier: Title or ID of the article.
            by: Search method — "title" or "id".

        Returns:
            Human-readable result string.
        """
        return self.information_system.view_article(identifier, by)

    def raw_list_by_category(self, category: str, entity_type: str, level: Optional[str] = None) -> str:
        """List clubs or advisors by category.

        Args:
            category: Category to filter by.
                Club categories: "Academic & Technological", "Sports & Fitness",
                    "Arts & Culture", "Community Service", "Professional Development",
                    "Special Interest".
                Advisor research areas: "Engineering", "Computer Science", "Mathematics",
                    "Physics", "Biology", "Chemistry", "Medicine", "Social Sciences",
                    "Humanities".
            entity_type: "club" or "advisor".
            level: For advisors only — "level_1" or "level_2" to restrict which research
                area level is searched. Omit to search all levels and tags.

        Campus data available: 101 student clubs, 1000 faculty advisors,
            395 library books.

        Returns:
            Human-readable result string.
        """
        return self.information_system.list_by_category(category, entity_type, level)

    def raw_query_by_identifier(self, identifier: str, by: str, entity_type: str) -> str:
        """Get all details for a specific club or advisor by name or ID.

        Args:
            identifier: Name or ID of the club/advisor.
            by: "name" or "id".
            entity_type: "club" or "advisor".

        Returns:
            Human-readable result string.
        """
        return self.information_system.query_by_identifier(identifier, by, entity_type)

    def raw_list_books_by_category(self, category: str) -> str:
        """List all library books in a category.

        Available library book categories include: Neuroscience, Political Science, AI,
        Computer Science, Mathematics, Physics, Biology, Chemistry, Literature, History,
        Engineering, Medicine, and more.

        Args:
            category: Category to filter by (e.g. "Computer Science").

        Returns:
            Human-readable result string.
        """
        return self.information_system.list_books_by_category(category)

    def raw_search_books(self, query: str, search_type: str = "title") -> str:
        """Search library books by title or author.

        Returns books with availability status (Available/Checked Out), call numbers,
        type, category, and location details.

        Args:
            query: Search query string.
            search_type: "title" (default) or "author".

        Returns:
            Human-readable result string.
        """
        return self.information_system.search_books(query, search_type)

    # Course selection / draft / registration
    def raw_browse_courses(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Browse available courses with optional filters.

        Course selection rules:
        - Semester 1: select at least 6 compulsory courses, 8 total.
            Compulsory pass budget: 1 S-Pass, 2 A-Passes, unlimited B-Passes.
            Elective pass budget: 1 A-Pass, unlimited B-Passes.
        - Semester 2: select at least 5 compulsory courses, 7 total.
            Compulsory pass budget: 1 S-Pass, 1 A-Pass, unlimited B-Passes.

        Pass guidelines:
        - S-Pass: guarantees enrollment for all courses, regardless of popularity.
        - A-Pass: guarantees enrollment for many courses, but not the most popular ones.
        - B-Pass: only usable for less popular courses.

        Available courses: 226 total (210 Semester 1, 16 Semester 2).
        Course types: "Compulsory" (46 courses), "Elective" (180 courses).

        **IMPORTANT** Many courses have multiple sections with different instructors and
        schedules. Each section has a unique section_id — e.g. "COMS0031131032"
        and "COMS0031131032(2)" are two different sections of the same course.
        When making pass changes to a course in your draft, you MUST use the EXACT section_id
        that is already in your draft (check with view_draft()).

        Args:
            filters: Optional dict to narrow results:
                - "course_code": partial match on course code.
                - "course_name": partial, case-insensitive match on course name.
                - "credits": filter expression (e.g. "<=3").

        Returns:
            List of dicts, each with keys: "section_id", "course_name",
            "credits", "type", "instructor", "popularity", "schedule".
        """
        return self.course_selection_system.browse_courses(filters)

    def raw_add_course(self, section_id: str) -> str:
        """Add a course to your draft schedule.

        Args:
            section_id: Section ID of the course to add (e.g. "WXK003111107").

        Returns:
            Human-readable result string.
        """
        return self.course_selection_system.add_course(section_id)

    def raw_remove_course(self, section_id: str) -> str:
        """Remove a course from your draft schedule.

        Args:
            section_id: Section ID of the course to remove.

        Returns:
            Human-readable result string.
        """
        return self.course_selection_system.remove_course(section_id)

    def raw_assign_pass(self, section_id: str, pass_type: str) -> str:
        """Assign a priority pass to a drafted course.

        Args:
            section_id: Section ID of the course.
            pass_type: "S-Pass", "A-Pass", or "B-Pass".

        Returns:
            Human-readable result string.
        """
        return self.course_selection_system.assign_pass(section_id, pass_type)

    def raw_view_draft(self) -> list[Dict[str, str]]:
        """View your current draft schedule.

        Returns:
            List of dicts, each with "course_code" and "assigned_pass" keys.
            Empty list if no courses in draft.
        """
        # DIFF from original: returns list of dicts instead of str.
        # Original: returned a formatted string like ``"Your draft: ..."``
        # Issue: agent needs course codes and pass types to decide what to change,
        # but had to parse them from a multi-line formatted string.
        # Fix: return list of {"course_code": ..., "assigned_pass": ...} dicts.

        draft = self.course_selection_system.get_draft_schedule_for_evaluation()
        return [
            {"course_code": s.course_code, "assigned_pass": s.assigned_pass or ""}
            for s in draft.selected_sections
        ]

    def raw_submit_draft(self) -> str:
        """Submit your draft schedule for final registration.

        Returns:
            Human-readable result string.
        """
        return self.course_selection_system.submit_draft()

    # Email
    def raw_send_email(self, recipient: str, subject: str, body: str) -> str:
        """Send an email.

        Args:
            recipient: Recipient email address.
            subject: Subject line.
            body: Email body content.

        Returns:
            Human-readable result string.
        """
        return self.email_system.send_email(recipient, subject, body)
