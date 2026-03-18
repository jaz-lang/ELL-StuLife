"""
Bibliography and Information Query System for CampusLifeBench
All natural language communications/returns MUST use English only
"""

import json
from typing import Dict, List, Any, Optional
from pathlib import Path

from ..tools import ensure_english_message


class InformationSystem:
    """
    Static information query system for bibliography and campus data
    Provides read-only access to structured book and campus information
    """

    def __init__(self, bibliography_path: Path, data_system_path: Path):
        """
        Initialize information system

        Args:
            bibliography_path: Path to bibliography JSON file
            data_system_path: Path to campus data JSON file
        """
        self.bibliography_path = bibliography_path
        self.data_system_path = data_system_path

        self._bibliography_data: Optional[Dict[str, Any]] = None
        self._data_system_data: Optional[Dict[str, Any]] = None

        self._load_data()

    def _load_data(self):
        """Load bibliography and data system data from JSON files"""
        # Load bibliography data
        try:
            with open(self.bibliography_path, 'r', encoding='utf-8') as f:
                self._bibliography_data = json.load(f)
        except FileNotFoundError:
            # Create minimal bibliography data if file doesn't exist
            self._bibliography_data = {
                "books": [
                    {
                        "book_title": "Introduction to Computer Science",
                        "chapters": [
                            {
                                "chapter_title": "Chapter 1: Fundamentals",
                                "sections": [
                                    {
                                        "section_title": "Section 1.1: Basic Concepts",
                                        "articles": [
                                            {
                                                "article_id": "cs_intro_001",
                                                "title": "What is Computer Science?",
                                                "body": "Computer science is the study of computational systems and the design of computer systems and their applications."
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }

        # Load data system data
        try:
            with open(self.data_system_path, 'r', encoding='utf-8') as f:
                self._data_system_data = json.load(f)
            # Ensure all library books are marked as "Available"
            if "library_books" in self._data_system_data:
                for book in self._data_system_data["library_books"]:
                    book["status"] = "Available"
        except FileNotFoundError:
            # Create minimal data system data if file doesn't exist
            self._data_system_data = {
                "clubs": [
                    {
                        "club_id": "C001",
                        "club_name": "Computer Science Club",
                        "category": "Academic",
                        "description": "A club for computer science enthusiasts",
                        "recruitment_info": "Open to all students interested in computer science"
                    }
                ],
                "advisors": [
                    {
                        "advisor_id": "T001",
                        "name": "Dr. John Smith",
                        "gender": "Male",
                        "age": 45,
                        "email": "john.smith@university.edu",
                        "research_area": {
                            "level_1": "Computer Science",
                            "level_2": "Artificial Intelligence",
                            "tags": ["Machine Learning", "Natural Language Processing"]
                        },
                        "representative_work": ["AI in Education", "NLP Applications"],
                        "preferences": {"meeting_time": "afternoon", "communication": "email"}
                    }
                ]
            }

    # ========== Bibliography Query Tools ==========

    def list_chapters(self, book_title: str) -> str:
        """
        List all chapters in the specified book

        Args:
            book_title: Title of the book

        Returns:
            Human-readable chapter list

        Raises:
            ValueError: If book_title is missing or book not found
        """
        if not book_title:
            raise ValueError("Book title is required.")

        # Find the book
        for book in self._bibliography_data["books"]:
            if book["book_title"].lower() == book_title.lower():
                chapters = [chapter["chapter_title"] for chapter in book["chapters"]]

                if chapters:
                    message = f"Book '{book_title}' contains the following chapters: {', '.join(chapters)}."
                else:
                    message = f"Book '{book_title}' has no chapters."

                # TODO: also return structured {"book_title": book["book_title"], "chapters": chapters}?
                # (originally part of ToolResult.data)
                return message

        raise ValueError(f"Book '{book_title}' not found.")

    def list_sections(self, book_title: str, chapter_title: str) -> str:
        """
        List all sections in the specified chapter

        Args:
            book_title: Title of the book
            chapter_title: Title of the chapter

        Returns:
            Human-readable section list

        Raises:
            ValueError: If inputs are missing or book/chapter not found
        """
        if not all([book_title, chapter_title]):
            raise ValueError("Both book title and chapter title are required.")

        # Find the book and chapter
        for book in self._bibliography_data["books"]:
            if book["book_title"].lower() == book_title.lower():
                for chapter in book["chapters"]:
                    if chapter["chapter_title"].lower() == chapter_title.lower():
                        sections = [section["section_title"] for section in chapter["sections"]]

                        if sections:
                            message = f"Chapter '{chapter_title}' in book '{book_title}' contains the following sections: {', '.join(sections)}."
                        else:
                            message = f"Chapter '{chapter_title}' in book '{book_title}' has no sections."

                        # TODO: also return structured {"book_title": book["book_title"], "chapter_title": chapter["chapter_title"], "sections": sections}?
                        # (originally part of ToolResult.data)
                        return message

                raise ValueError(f"Chapter '{chapter_title}' not found in book '{book_title}'.")

        raise ValueError(f"Book '{book_title}' not found.")

    def list_articles(self, book_title: str, chapter_title: str, section_title: str) -> str:
        """
        List all articles in the specified section

        Args:
            book_title: Title of the book
            chapter_title: Title of the chapter
            section_title: Title of the section

        Returns:
            Human-readable article list

        Raises:
            ValueError: If inputs are missing or book/chapter/section not found
        """
        if not all([book_title, chapter_title, section_title]):
            raise ValueError("Book title, chapter title, and section title are all required.")

        # Find the book, chapter, and section
        for book in self._bibliography_data["books"]:
            if book["book_title"].lower() == book_title.lower():
                for chapter in book["chapters"]:
                    if chapter["chapter_title"].lower() == chapter_title.lower():
                        for section in chapter["sections"]:
                            if section["section_title"].lower() == section_title.lower():
                                articles = [article["title"] for article in section["articles"]]

                                if articles:
                                    message = f"Section '{section_title}' contains the following articles: {', '.join(articles)}."
                                else:
                                    message = f"Section '{section_title}' has no articles."

                                # TODO: also return structured {"book_title": book["book_title"], "chapter_title": chapter["chapter_title"], "section_title": section["section_title"], "articles": articles}?
                                # (originally part of ToolResult.data)
                                return message

                        raise ValueError(f"Section '{section_title}' not found in chapter '{chapter_title}'.")

                raise ValueError(f"Chapter '{chapter_title}' not found in book '{book_title}'.")

        raise ValueError(f"Book '{book_title}' not found.")

    def view_article(self, identifier: str, by: str) -> str:
        """
        View the full content of an article

        Args:
            identifier: Article title or ID
            by: Search method - "title" or "id"

        Returns:
            Human-readable article content

        Raises:
            ValueError: If inputs are missing/invalid or article not found
        """
        if not all([identifier, by]):
            raise ValueError("Both identifier and search method ('by') are required.")

        if by not in ["title", "id"]:
            raise ValueError("Search method must be either 'title' or 'id'.")

        # Search through all articles
        for book in self._bibliography_data["books"]:
            for chapter in book["chapters"]:
                for section in chapter["sections"]:
                    for article in section["articles"]:
                        if by == "title" and article["title"].lower() == identifier.lower():
                            # TODO: also return the raw article dict? (originally part of ToolResult.data)
                            return f"Article: {article['title']}\n\n{article['body']}"
                        elif by == "id" and article["article_id"] == identifier:
                            # TODO: also return the raw article dict? (originally part of ToolResult.data)
                            return f"Article: {article['title']}\n\n{article['body']}"

        raise ValueError(f"Article with {by} '{identifier}' not found.")

    # ========== Data System Query Tools ==========

    def list_by_category(self, category: str, entity_type: str, level: Optional[str] = None) -> str:
        """
        List entities by category

        Args:
            category: Category to filter by
            entity_type: "club" or "advisor"
            level: For advisors only - "level_1" or "level_2"

        Returns:
            Human-readable list of matching entities

        Raises:
            ValueError: If inputs are missing or invalid
        """
        if not all([category, entity_type]):
            raise ValueError("Both category and entity_type are required.")

        if entity_type not in ["club", "advisor"]:
            raise ValueError("Entity type must be either 'club' or 'advisor'.")

        results = []

        if entity_type == "club":
            for club in self._data_system_data["clubs"]:
                if club["category"].lower() == category.lower():
                    results.append(club["club_name"])

            if results:
                message = f"Clubs in category '{category}': {', '.join(results)}."
            else:
                message = f"No clubs found in category '{category}'."

            # TODO: also return structured {"clubs": results}? (originally part of ToolResult.data)
            return message

        elif entity_type == "advisor":
            for advisor in self._data_system_data["advisors"]:
                research_area = advisor.get("research_area", {})

                if level == "level_1" and research_area.get("level_1", "").lower() == category.lower():
                    results.append({
                        "name": advisor["name"],
                        "research_area": research_area,
                        "representative_work": advisor.get("representative_work", [])
                    })
                elif level == "level_2" and research_area.get("level_2", "").lower() == category.lower():
                    results.append({
                        "name": advisor["name"],
                        "research_area": research_area,
                        "representative_work": advisor.get("representative_work", [])
                    })
                elif level is None:
                    # Search in both levels and tags
                    if (category.lower() in research_area.get("level_1", "").lower() or
                            category.lower() in research_area.get("level_2", "").lower() or
                            any(category.lower() in tag.lower() for tag in research_area.get("tags", []))):
                        results.append({
                            "name": advisor["name"],
                            "research_area": research_area,
                            "representative_work": advisor.get("representative_work", [])
                        })

            if results:
                message = f"Found {len(results)} advisor(s) in category '{category}':"
                for advisor in results:
                    message += f"\n- Name: {advisor['name']}"

                    # Format research area
                    research_area = advisor.get('research_area', {})
                    level1 = research_area.get('level_1', 'N/A')
                    level2 = research_area.get('level_2', 'N/A')
                    message += f"\n  Research Area: {level1} -> {level2}"

                    tags = research_area.get('tags', [])
                    if tags:
                        message += f"\n  Tags: {', '.join(tags)}"

                    # Format representative work
                    rep_work = advisor.get('representative_work', [])
                    if rep_work:
                        work_items = '\n    - '.join(rep_work)
                        message += f"\n  Representative Work:\n    - {work_items}"
            else:
                message = f"No advisors found in category '{category}'."

            # TODO: also return structured {"advisors": results}? (originally part of ToolResult.data)
            return message

    def query_by_identifier(self, identifier: str, by: str, entity_type: str) -> str:
        """
        Query entity by identifier (name or ID)

        Args:
            identifier: Entity name or ID
            by: Search method - "name" or "id"
            entity_type: "club" or "advisor"

        Examples:
            >>> # Query a club by its ID
            >>> query_by_identifier(identifier="C001", by="id", entity_type="club")
            >>> # Query a club by its name
            >>> query_by_identifier(identifier="Computer Science Club", by="name", entity_type="club")
            >>> # Query an advisor by their ID
            >>> query_by_identifier(identifier="T001", by="id", entity_type="advisor")
            >>> # Query an advisor by their name
            >>> query_by_identifier(identifier="Dr. John Smith", by="name", entity_type="advisor")

        Returns:
            Human-readable entity details

        Raises:
            ValueError: If inputs are missing/invalid or entity not found
        """
        if not all([identifier, by, entity_type]):
            raise ValueError("Identifier, search method ('by'), and entity_type are all required.")

        if by not in ["name", "id"]:
            raise ValueError("Search method must be either 'name' or 'id'.")

        if entity_type not in ["club", "advisor"]:
            raise ValueError("Entity type must be either 'club' or 'advisor'.")

        if entity_type == "club":
            for club in self._data_system_data["clubs"]:
                if ((by == "name" and club["club_name"].lower() == identifier.lower()) or
                        (by == "id" and club["club_id"] == identifier)):

                    message = f"Club Details:\n"
                    message += f"Name: {club['club_name']}\n"
                    message += f"ID: {club['club_id']}\n"
                    message += f"Category: {club['category']}\n"
                    message += f"Description: {club['description']}\n"
                    message += f"Recruitment Info: {club['recruitment_info']}"

                    # TODO: also return the raw club dict? (originally part of ToolResult.data)
                    return message

            raise ValueError(f"Club with {by} '{identifier}' not found.")

        elif entity_type == "advisor":
            for advisor in self._data_system_data["advisors"]:
                if ((by == "name" and advisor["name"].lower() == identifier.lower()) or
                        (by == "id" and advisor["advisor_id"] == identifier)):

                    message = f"Advisor Details:\n"
                    message += f"Name: {advisor['name']}\n"
                    message += f"ID: {advisor['advisor_id']}\n"
                    message += f"Email: {advisor['email']}\n"
                    message += f"Research Area: {advisor['research_area']['level_2']}\n"
                    message += f"Representative Work: {', '.join(advisor['representative_work'])}"

                    # TODO: also return the raw advisor dict? (originally part of ToolResult.data)
                    return message

            raise ValueError(f"Advisor with {by} '{identifier}' not found.")

    # ========== Library Books Query Tools ==========

    def list_books_by_category(self, category: str) -> str:
        """
        List all library books by category

        Args:
            category: Category to filter by

        Returns:
            Human-readable list of matching books

        Raises:
            ValueError: If category is missing or library books data not available
        """
        if not category:
            raise ValueError("Category is required.")

        if "library_books" not in self._data_system_data:
            raise ValueError("Library books data not available.")

        matching_books = []
        for book in self._data_system_data["library_books"]:
            if book.get("category", "").lower() == category.lower():
                matching_books.append({
                    "title": book.get("title", ""),
                    "author": book.get("author", ""),
                    "call_number": book.get("call_number", ""),
                    "status": book.get("status", "Available"),
                    "type": book.get("type", ""),
                    "category": book.get("category", ""),
                    "location": book.get("location", "")
                })

        if matching_books:
            message = f"Found {len(matching_books)} book(s) in category '{category}':"
            for book in matching_books:
                status_indicator = "✓" if book["status"] == "Available" else "✗"
                message += f"\n- {status_indicator} \"{book['title']}\" by {book['author']} (Call Number: {book['call_number']}, Type: {book['type']}, Location: {book['location']})"
        else:
            message = f"No books found in category '{category}'."

        # TODO: also return structured {"books": matching_books}? (originally part of ToolResult.data)
        return message

    def search_books(self, query: str, search_type: str = "title") -> str:
        """
        Search library books by title or author

        Args:
            query: Search query string
            search_type: "title" or "author"

        Returns:
            Human-readable list of matching books

        Raises:
            ValueError: If query is missing, search_type is invalid, or library data unavailable
        """
        if not query:
            raise ValueError("Search query is required.")

        if search_type not in ["title", "author"]:
            raise ValueError("Search type must be either 'title' or 'author'.")

        if "library_books" not in self._data_system_data:
            raise ValueError("Library books data not available.")

        matching_books = []
        query_lower = query.lower()

        for book in self._data_system_data["library_books"]:
            match = False
            if search_type == "title":
                match = query_lower in book.get("title", "").lower()
            elif search_type == "author":
                match = query_lower in book.get("author", "").lower()

            if match:
                matching_books.append({
                    "title": book.get("title", ""),
                    "author": book.get("author", ""),
                    "call_number": book.get("call_number", ""),
                    "status": book.get("status", "Available"),
                    "type": book.get("type", ""),
                    "category": book.get("category", ""),
                    "location": book.get("location", "")
                })

        if matching_books:
            message = f"Found {len(matching_books)} book(s) matching '{query}' in {search_type}:"
            for book in matching_books:
                status_indicator = "✓" if book["status"] == "Available" else "✗"
                message += f"\n- {status_indicator} \"{book['title']}\" by {book['author']} ({book['category']}, Call Number: {book['call_number']}, Type: {book['type']}, Location: {book['location']})"
        else:
            message = f"No books found matching '{query}' in {search_type}."

        # TODO: also return structured {"books": matching_books}? (originally part of ToolResult.data)
        return message

    def get_campus_data(self) -> Optional[Dict[str, Any]]:
        """
        Get the raw campus data dictionary

        Returns:
            A dictionary containing all campus data, or None if not loaded
        """
        return self._data_system_data
