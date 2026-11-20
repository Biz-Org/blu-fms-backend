# -*- coding: utf-8 -*-
"""Shared selection constants for Asset Management."""

CLASSIFICATION_LEVELS = [
    ("category", "Category"),
    ("type", "Asset Type"),
    ("subtype", "Sub-Type"),
]

LOCATION_TYPES = [
    ("property", "Property / Site"),
    ("building", "Building / Tower"),
    ("floor", "Floor"),
    ("wing_area", "Wing / Area"),
    ("room", "Room / Location"),
]

LIFECYCLE_STATES = [
    ("draft", "Draft"),
    ("active", "Active"),
    ("under_maintenance", "Under Maintenance"),
    ("inactive", "Inactive"),
    ("disposed", "Disposed"),
]

CONDITION_STATES = [
    ("excellent", "Excellent"),
    ("good", "Good"),
    ("fair", "Fair"),
    ("poor", "Poor"),
    ("critical", "Critical"),
]

HEALTH_STATUSES = [
    ("healthy", "Healthy"),
    ("attention", "Requires Attention"),
    ("degraded", "Degraded"),
    ("unknown", "Unknown"),
]

CRITICALITY_LEVELS = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

DEPRECIATION_METHODS = [
    ("straight_line", "Straight Line"),
    ("declining", "Declining Balance"),
    ("units", "Units of Production"),
    ("manual", "Manual / External"),
]
