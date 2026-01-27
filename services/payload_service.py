#!/usr/bin/env python3
"""
Payload Service - Unified service for managing all payload creators
Handles all 8 payload types with their specific parameter requirements
"""

import subprocess
import sys
import json
import logging
import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

# Import country mapper
from services.country_mapper import country_mapper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PayloadService:
    """Service for managing payload generation across all payload creators"""
    
    def __init__(self):
        # Get the absolute path to scrapers directory relative to this service file
        service_dir = Path(__file__).parent.absolute()
        data_extractor_dir = service_dir.parent
        self.scrapers_dir = data_extractor_dir / "scrapers"
        self.payload_creators = {
            "comparemarket": {
                "script": "macmap/comparemarket/comparemarketPayloadCreator.py",
                "name": "Compare Market",
                "description": "Generate payloads for market comparison analysis",
                "fields": ["countries", "hscodes"]
            },
            "competitors": {
                "script": "macmap/competitors/competitorsPayloadCreator.py",
                "name": "Competitors",
                "description": "Generate payloads for competitor analysis",
                "fields": ["countries", "hscodes"]
            },
            "eximpedia": {
                "script": "eximpedia/eximPediaPayloadCreator.py",
                "name": "Eximpedia",
                "description": "Generate Eximpedia trade data payloads",
                "fields": ["hscode", "country", "mode", "start_date", "end_date"]
            },
            "fulltariff": {
                "script": "macmap/fulltariff/fulltariffPayloadCreator.py",
                "name": "Full Tariff",
                "description": "Generate comprehensive tariff data payloads",
                "fields": ["countries"]
            },
            "indiantradeportal": {
                "script": "indiantradeportal/indiantradeportalPayloadCreator.py",
                "name": "Indian Trade Portal", 
                "description": "Create payloads for Indian trade data",
                "fields": ["hscode"]
            },
            "macmapproduct": {
                "script": "macmap/product/macmapproductPayloadCreator.py",
                "name": "MacMap Product",
                "description": "Generate MacMap product analysis payloads",
                "fields": ["countries", "hsc_lvl"]
            },
            "macmapregulatory": {
                "script": "macmap/regulatory/macmapregulatoryPayloadCreator.py",
                "name": "MacMap Regulatory",
                "description": "Create regulatory requirements payloads",
                "fields": ["country1", "country2", "hsc", "regtype"]
            },
            "macmaptariff": {
                "script": "macmap/tariff/macmapTariffPayloadCreator.py",
                "name": "MacMap Tariff",
                "description": "Generate MacMap tariff analysis payloads",
                "fields": ["country1", "country2", "hscodes", "year"]
            },
            "traderemedies": {
                "script": "macmap/traderemedies/tradeRemediesPayloadCreator.py",
                "name": "Trade Remedies",
                "description": "Generate trade remedies analysis payloads",
                "fields": ["countries", "hscodes"]
            },
            "trademap": {
                "script": "trademap/tradeMapPayloadCreator.py",
                "name": "TradeMap",
                "description": "Create TradeMap data scraping payloads",
                "fields": ["country1", "country2", "hscodes"]
            }
        }
        
    def get_available_creators(self) -> Dict[str, Dict[str, str]]:
        """Get list of available payload creators"""
        return self.payload_creators
    
    def _normalize_config(self, payload_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize frontend config to backend expected format"""
        normalized = config.copy()
        
        # Convert hsCodes OR hscodes (array from frontend) to hscode/hscodes/hsc (string for backend)
        # Handle both camelCase (hsCodes) and lowercase (hscodes) from form
        hs_codes_key = None
        if 'hsCodes' in normalized:
            hs_codes_key = 'hsCodes'
        elif 'hscodes' in normalized:
            hs_codes_key = 'hscodes'
        
        if hs_codes_key:
            hs_codes = normalized[hs_codes_key]
            if isinstance(hs_codes, list):
                hs_codes_str = ','.join(hs_codes)
            else:
                hs_codes_str = str(hs_codes)
            
            # Different scrapers expect different field names
            if payload_type in ["indiantradeportal", "eximpedia"]:
                normalized['hscode'] = hs_codes_str
            elif payload_type == "macmapregulatory":
                normalized['hsc'] = hs_codes_str
            else:
                # Keep as hscodes for macmaptariff, trademap, etc.
                normalized['hscodes'] = hs_codes_str
            
            # Only delete the original key if it's different from the target
            if hs_codes_key in normalized and hs_codes_key != 'hscodes':
                del normalized[hs_codes_key]
        
        # Convert countries array to comma-separated string
        if 'countries' in normalized and isinstance(normalized['countries'], list):
            normalized['countries'] = ','.join(normalized['countries'])
        
        # For eximpedia, rename countries to country (singular)
        if payload_type == "eximpedia" and 'countries' in normalized:
            normalized['country'] = normalized['countries']
            del normalized['countries']
        
        # For trademap, keep importing/exporting countries separate for proper combinations
        if payload_type == "trademap":
            if 'exporting_countries' in normalized and 'importing_countries' in normalized:
                # Convert to comma-separated strings for payload creator
                exp = normalized['exporting_countries'] if isinstance(normalized['exporting_countries'], list) else [normalized['exporting_countries']]
                imp = normalized['importing_countries'] if isinstance(normalized['importing_countries'], list) else [normalized['importing_countries']]
                normalized['country1'] = ','.join(exp)  # Exporting countries
                normalized['country2'] = ','.join(imp)  # Importing countries
                del normalized['exporting_countries']
                del normalized['importing_countries']
            
            # Pass through new trademap options (time_series_types, view_types, values_types)
            # These are already in the correct format from the frontend
        
        # For macmaptariff, keep importing/exporting countries separate for proper combinations
        if payload_type == "macmaptariff":
            if 'exporting_countries' in normalized and 'importing_countries' in normalized:
                # Convert to comma-separated strings for payload creator
                exp = normalized['exporting_countries'] if isinstance(normalized['exporting_countries'], list) else [normalized['exporting_countries']]
                imp = normalized['importing_countries'] if isinstance(normalized['importing_countries'], list) else [normalized['importing_countries']]
                normalized['country1'] = ','.join(imp)  # Importing countries (reporter)
                normalized['country2'] = ','.join(exp)  # Exporting countries (partner)
                del normalized['exporting_countries']
                del normalized['importing_countries']
        
        # Convert importingCountry/exportingCountry arrays to comma-separated strings
        if 'importingCountry' in normalized:
            if isinstance(normalized['importingCountry'], list):
                normalized['importingCountry'] = ','.join(normalized['importingCountry'])
        
        if 'exportingCountry' in normalized:
            if isinstance(normalized['exportingCountry'], list):
                normalized['exportingCountry'] = ','.join(normalized['exportingCountry'])
        
        # For macmapregulatory, map directly to country1 and country2
        # Keep as comma-separated strings to create all combinations in payload creator
        if payload_type == "macmapregulatory":
            if 'importingCountry' in normalized and 'exportingCountry' in normalized:
                # Keep as comma-separated for Cartesian product
                normalized['country1'] = normalized['importingCountry']
                normalized['country2'] = normalized['exportingCountry']
                del normalized['importingCountry']
                del normalized['exportingCountry']
        # For other 2-country scrapers, combine into single countries field
        elif 'importingCountry' in normalized and 'exportingCountry' in normalized:
            # Combine both countries
            importing = normalized['importingCountry']
            exporting = normalized['exportingCountry']
            normalized['countries'] = f"{importing},{exporting}"
        
        # Convert hsLevel to hsc_lvl
        if 'hsLevel' in normalized:
            normalized['hsc_lvl'] = normalized['hsLevel']
            del normalized['hsLevel']
        
        # Convert tradeType to mode for eximpedia
        if payload_type == "eximpedia" and 'tradeType' in normalized:
            normalized['mode'] = normalized['tradeType']
            del normalized['tradeType']
        
        # Convert startDate/endDate for eximpedia - convert to MM/DD/YYYY format (with leading zeros)
        if payload_type == "eximpedia":
            if 'startDate' in normalized and normalized['startDate']:
                # Parse and convert to MM/DD/YYYY format (with leading zeros for scraper)
                try:
                    from datetime import datetime
                    # Try MM/DD/YYYY format first (e.g., 01/30/2025 = Jan 30)
                    date_obj = datetime.strptime(normalized['startDate'], '%m/%d/%Y')
                    normalized['start_date'] = date_obj.strftime('%m/%d/%Y')  # Keep MM/DD/YYYY
                except:
                    try:
                        # Try DD/MM/YYYY format (e.g., 30/01/2025 = Jan 30)
                        date_obj = datetime.strptime(normalized['startDate'], '%d/%m/%Y')
                        normalized['start_date'] = date_obj.strftime('%m/%d/%Y')  # Convert to MM/DD/YYYY
                    except:
                        try:
                            # Try YYYY-MM-DD format
                            date_obj = datetime.strptime(normalized['startDate'], '%Y-%m-%d')
                            normalized['start_date'] = date_obj.strftime('%m/%d/%Y')  # Convert to MM/DD/YYYY
                        except:
                            # If it's just a year, convert to 01/01/YYYY
                            try:
                                year = int(normalized['startDate'])
                                if 2000 <= year <= 2030:
                                    normalized['start_date'] = f"01/01/{year}"
                            except:
                                pass
                if 'startDate' in normalized:
                    del normalized['startDate']
            
            if 'endDate' in normalized and normalized['endDate']:
                try:
                    from datetime import datetime
                    # Try MM/DD/YYYY format first (e.g., 01/30/2025 = Jan 30)
                    date_obj = datetime.strptime(normalized['endDate'], '%m/%d/%Y')
                    normalized['end_date'] = date_obj.strftime('%m/%d/%Y')  # Keep MM/DD/YYYY
                except:
                    try:
                        # Try DD/MM/YYYY format (e.g., 30/01/2025 = Jan 30)
                        date_obj = datetime.strptime(normalized['endDate'], '%d/%m/%Y')
                        normalized['end_date'] = date_obj.strftime('%m/%d/%Y')  # Convert to MM/DD/YYYY
                    except:
                        try:
                            # Try YYYY-MM-DD format
                            date_obj = datetime.strptime(normalized['endDate'], '%Y-%m-%d')
                            normalized['end_date'] = date_obj.strftime('%m/%d/%Y')  # Convert to MM/DD/YYYY
                        except:
                            # If it's just a year, convert to 12/31/YYYY
                            try:
                                year = int(normalized['endDate'])
                                if 2000 <= year <= 2030:
                                    normalized['end_date'] = f"12/31/{year}"
                            except:
                                pass
                if 'endDate' in normalized:
                    del normalized['endDate']
            
            # If dates weren't provided or parsing failed, use current year as default
            if 'start_date' not in normalized:
                from datetime import datetime
                current_year = datetime.now().year
                normalized['start_date'] = f"1/1/{current_year}"
            if 'end_date' not in normalized:
                from datetime import datetime
                current_year = datetime.now().year
                normalized['end_date'] = f"31/12/{current_year}"
        
        # Convert regulationType to regtype (and convert to lowercase)
        if 'regulationType' in normalized:
            regtype_value = normalized['regulationType']
            # Convert to lowercase and handle both string and list
            if isinstance(regtype_value, str):
                normalized['regtype'] = regtype_value.lower()
            elif isinstance(regtype_value, list):
                normalized['regtype'] = [r.lower() if isinstance(r, str) else r for r in regtype_value]
            else:
                normalized['regtype'] = regtype_value
            del normalized['regulationType']
        
        # For macmapregulatory, split countries into country1 and country2 (if not already done)
        if payload_type == "macmapregulatory" and 'countries' in normalized:
            countries_str = normalized['countries']
            if isinstance(countries_str, str):
                countries_list = [c.strip() for c in countries_str.split(',') if c.strip()]
            else:
                countries_list = countries_str
            
            # Split into country1 and country2
            if len(countries_list) >= 2:
                # First half as country1, second half as country2
                mid = len(countries_list) // 2
                normalized['country1'] = ','.join(countries_list[:mid])
                normalized['country2'] = ','.join(countries_list[mid:])
            elif len(countries_list) == 1:
                # Use same country for both
                normalized['country1'] = countries_list[0]
                normalized['country2'] = countries_list[0]
            else:
                normalized['country1'] = ''
                normalized['country2'] = ''
            
            # Remove the combined countries field
            del normalized['countries']
        
        # Convert all country codes to full names
        self._convert_country_codes_to_names(normalized)
        
        return normalized
    
    def _convert_country_codes_to_names(self, config: Dict[str, Any]):
        """Convert country codes to full names in-place"""
        # Fields that contain country codes
        country_fields = ['country1', 'country2', 'countries', 'importingCountry', 'exportingCountry']
        
        for field in country_fields:
            if field in config and config[field]:
                value = config[field]
                if isinstance(value, str):
                    # Convert comma-separated codes to names
                    config[field] = country_mapper.convert_country_list(value)
                elif isinstance(value, list):
                    # Convert list of codes to names
                    config[field] = [country_mapper.get_country_name(code) for code in value]
    
    def validate_config(self, payload_type: str, config: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """Validate configuration for a payload type and return normalized config"""
        if payload_type not in self.payload_creators:
            return False, f"Invalid payload type: {payload_type}", {}
        
        # Normalize config first
        normalized_config = self._normalize_config(payload_type, config)
        
        # Debug logging
        logger.info(f"Validating {payload_type}")
        logger.info(f"Original config: {config}")
        logger.info(f"Normalized config: {normalized_config}")
        
        creator_info = self.payload_creators[payload_type]
        required_fields = creator_info["fields"]
        
        # Validate required fields based on payload type
        for field in required_fields:
            if field not in normalized_config:
                logger.error(f"Missing required field '{field}' for {payload_type}. Normalized config: {normalized_config}")
                return False, f"Field '{field}' is required for {payload_type}", {}
            # Check if field is empty (but allow False for booleans)
            value = normalized_config[field]
            if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and len(value) == 0):
                logger.error(f"Required field '{field}' is empty for {payload_type}. Normalized config: {normalized_config}")
                return False, f"Field '{field}' is required for {payload_type}", {}
        
        # Type-specific validations (beyond required field checks)
        validation_result = (True, "Configuration is valid")
        
        if payload_type == "comparemarket":
            validation_result = self._validate_comparemarket(normalized_config)
        elif payload_type == "competitors":
            validation_result = self._validate_comparemarket(normalized_config)
        elif payload_type == "eximpedia":
            validation_result = self._validate_eximpedia(normalized_config)
        elif payload_type == "macmapproduct":
            validation_result = self._validate_macmapproduct(normalized_config)
        # For trademap, skip additional validation - required fields already checked above
        # This allows optional fields like email, password, booleans, lists to pass through
        elif payload_type == "trademap":
            validation_result = (True, "Configuration is valid")
        elif payload_type in ["fulltariff", "macmapregulatory", "macmaptariff", "traderemedies"]:
            validation_result = self._validate_simple_fields(normalized_config, required_fields)
        elif payload_type == "indiantradeportal":
            validation_result = self._validate_simple_fields(normalized_config, required_fields)
        
        # Return validation result with normalized config
        return validation_result[0], validation_result[1], normalized_config
    
    def _validate_comparemarket(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate comparemarket and competitors config"""
        # Validate HS codes format (should be 6 digits)
        hscodes = config["hscodes"]
        if isinstance(hscodes, str):
            hscodes = [c.strip() for c in hscodes.split(",") if c.strip()]
        
        for hscode in hscodes:
            if not hscode.isdigit() or len(hscode) != 6:
                return False, f"Invalid HS code format: {hscode}. Must be 6 digits."
        
        return True, "Configuration is valid"
    
    def _validate_eximpedia(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate eximpedia specific config"""
        # Validate dates
        try:
            from datetime import datetime
            
            # Parse start_date - handle MM/DD/YYYY format
            try:
                start_date = datetime.strptime(config["start_date"], '%m/%d/%Y')
            except:
                return False, "start_date must be in MM/DD/YYYY format"
            
            # Parse end_date - handle MM/DD/YYYY format
            try:
                end_date = datetime.strptime(config["end_date"], '%m/%d/%Y')
            except:
                return False, "end_date must be in MM/DD/YYYY format"
            
            # Validate date range
            if start_date > end_date:
                return False, "Start date cannot be after end date"
                
        except KeyError as e:
            return False, f"Missing required date field: {e}"
        except Exception as e:
            return False, f"Date validation error: {str(e)}"
        
        # Validate mode
        if config["mode"] not in ["import", "export"]:
            return False, "Mode must be 'import' or 'export'"
        
        return True, "Configuration is valid"
    
    def _validate_macmapproduct(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate macmapproduct specific config"""
        # Validate hsc_lvl
        try:
            hsc_lvl = int(config.get("hsc_lvl", "6"))
            if hsc_lvl not in [2, 4, 6]:
                return False, "HS Code Level must be 2, 4, or 6"
        except ValueError:
            return False, "HS Code Level must be a valid number (2, 4, or 6)"
        
        # Validate countries
        countries = config.get("countries", "")
        if not countries or not countries.strip():
            return False, "Countries field cannot be empty"
        
        return True, "Configuration is valid"
    
    def _validate_simple_fields(self, config: Dict[str, Any], required_fields: List[str] = None) -> Tuple[bool, str]:
        """Validate simple field configs (most payload types)"""
        # If required_fields provided, only validate those fields
        # Otherwise validate all fields (old behavior)
        fields_to_check = required_fields if required_fields else config.keys()
        
        for field in fields_to_check:
            if field not in config:
                continue
                
            value = config[field]
            
            # Skip boolean fields - False is a valid value
            if isinstance(value, bool):
                continue
            # Skip list fields - empty lists are handled elsewhere
            if isinstance(value, list):
                continue
            # Check string fields
            if isinstance(value, str) and not value.strip():
                return False, f"Field '{field}' cannot be empty"
            # Check None values (but not False)
            if value is None:
                return False, f"Field '{field}' cannot be empty"
        
        return True, "Configuration is valid"
    
    def generate_payload(self, payload_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate payloads for the specified type"""
        try:
            # Validate configuration and get normalized config
            is_valid, message, normalized_config = self.validate_config(payload_type, config)
            if not is_valid:
                return {"success": False, "message": message}
            
            # Get the script for this payload type
            creator_info = self.payload_creators[payload_type]
            script_path = self.scrapers_dir / creator_info["script"]
            
            if not script_path.exists():
                return {"success": False, "message": f"Script not found: {script_path}"}
            
            # Prepare the script execution based on payload type using normalized config
            result = self._run_payload_script(payload_type, script_path, normalized_config)
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating payload for {payload_type}: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def _run_payload_script(self, payload_type: str, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run the payload generation script with the given configuration"""
        try:
            # For macmaptariff and trademap, create tasks directly instead of using script
            if payload_type == "macmaptariff":
                return self._create_macmap_tasks_directly(config)
            elif payload_type == "trademap":
                return self._create_trademap_tasks_directly(config)
            # Use programmatic mode for macmapregulatory, indiantradeportal, and eximpedia
            elif payload_type in ["macmapregulatory", "indiantradeportal", "eximpedia"]:
                return self._run_programmatic_script(script_path, config)
            # Prepare script input based on payload type
            elif payload_type == "comparemarket":
                return self._run_comparemarket_script(script_path, config)
            elif payload_type == "competitors":
                return self._run_competitors_script(script_path, config)
            elif payload_type in ["fulltariff", "macmapproduct", "macmaptariff", "traderemedies", "trademap"]:
                return self._run_sqlite_style_script(script_path, config)
            else:
                return {"success": False, "message": f"Unsupported payload type: {payload_type}"}
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Script execution timed out after 5 minutes"
            }
        except Exception as e:
            logger.error(f"Error running script {script_path}: {str(e)}")
            return {
                "success": False,
                "message": f"Script execution error: {str(e)}"
            }
    
    def _run_comparemarket_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run comparemarket script with specific format"""
        # Convert config to script format
        countries = self._parse_csv_field(config["countries"])
        hscodes = self._parse_csv_field(config["hscodes"])
        
        # Create input for the script
        script_input = []
        
        # Add bulk mode selection (2 for bulk mode, always use bulk)
        script_input.append("2")
        
        # Add HS codes
        script_input.append(",".join(hscodes))
        
        # Add countries  
        script_input.append(",".join(countries))
        
        input_text = "\n".join(script_input) + "\n"
        
        return self._execute_script(script_path, input_text)
    
    def _run_competitors_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run competitors script with specific format"""
        # Convert config to script format
        countries = self._parse_csv_field(config["countries"])
        hscodes = self._parse_csv_field(config["hscodes"])
        
        # Create input for the script
        script_input = []
        
        # Add bulk mode selection (2 for bulk mode, always use bulk)
        script_input.append("2")
        
        # Add HS codes
        script_input.append(",".join(hscodes))
        
        # Add countries  
        script_input.append(",".join(countries))
        
        input_text = "\n".join(script_input) + "\n"
        
        return self._execute_script(script_path, input_text)
    
    def _run_eximpedia_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run eximpedia script with specific format"""
        countries = self._parse_csv_field(config["countries"])
        hscodes = self._parse_csv_field(config["hscodes"])
        mode = config["mode"]
        from_year = config["from_year"]
        to_year = config["to_year"]
        
        # Create input for the script
        script_input = []
        
        # Add mode selection (1 for import, 2 for export)
        script_input.append("1" if mode == "import" else "2")
        
        # Add countries
        script_input.append(",".join(countries))
        
        # Add HS codes
        script_input.append(",".join(hscodes))
        
        # Add years
        script_input.append(str(from_year))
        script_input.append(str(to_year))
        
        # Add confirmation
        script_input.append("y")
        
        input_text = "\n".join(script_input) + "\n"
        
        return self._execute_script(script_path, input_text)
    
    def _run_sqlite_style_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run SQLite-style scripts that use interactive input"""
        # Create input for the script
        script_input = []
        
        # Most scripts have a menu: option 1 for interactive mode
        script_input.append("1")
        
        # Add field values based on the script type
        if "eximpedia" in str(script_path).lower():
            # ExImPedia needs: mode, countries, hscodes, from_year, to_year, confirmation
            mode = config.get("mode", "import")
            script_input.append("1" if mode == "import" else "2")
            script_input.append(",".join(self._parse_csv_field(config.get("countries", ""))))
            script_input.append(",".join(self._parse_csv_field(config.get("hscodes", ""))))
            script_input.append(str(config.get("from_year", "2020")))
            script_input.append(str(config.get("to_year", "2025")))
            script_input.append("y")
        elif "macmapproduct" in str(script_path).lower():
            # MacMap Product needs: countries, hsc_lvl, confirmation
            script_input.append(",".join(self._parse_csv_field(config.get("countries", ""))))
            script_input.append(str(config.get("hsc_lvl", "6")))
            script_input.append("y")
        elif "macmaptariff" in str(script_path).lower():
            # MacMap Tariff needs: year, hscodes, countries, confirmation
            script_input.append(str(config.get("year", "2024")))  # Year input
            script_input.append(",".join(self._parse_csv_field(config.get("hscodes", ""))))  # HS codes
            script_input.append(",".join(self._parse_csv_field(config.get("countries", ""))))  # Countries
            script_input.append("y")  # Confirmation
        elif "traderemedies" in str(script_path).lower():
            # Trade Remedies needs: year, hscodes, countries, confirmation
            script_input.append(str(config.get("year", "2024")))  # Year input
            script_input.append(",".join(self._parse_csv_field(config.get("hscodes", ""))))  # HS codes
            script_input.append(",".join(self._parse_csv_field(config.get("countries", ""))))  # Countries
            script_input.append("y")  # Confirmation
        elif "macmapregulatory" in str(script_path).lower():
            # MacMap Regulatory needs: country1, country2, hscodes, regtype, confirmation
            # Split countries into country1 and country2
            countries = self._parse_csv_field(config.get("countries", ""))
            
            # For regulatory, we need pairs of countries (country1, country2)
            # If only one country provided, use it for both
            if len(countries) == 1:
                country1 = countries[0]
                country2 = countries[0]
            elif len(countries) >= 2:
                # Use first as country1, rest as country2
                country1 = countries[0]
                country2 = ",".join(countries[1:])
            else:
                country1 = ""
                country2 = ""
            
            script_input.append(country1)  # Reporter Country (country1)
            script_input.append(country2)  # Partner Country (country2)
            script_input.append(",".join(self._parse_csv_field(config.get("hscodes", ""))))  # HS codes
            script_input.append(",".join(self._parse_csv_field(config.get("regtype", "i"))))  # Regulation type
            script_input.append("y")  # Confirmation
        elif "fulltariff" in str(script_path).lower():
            # FullTariff needs: countries, confirmation
            script_input.append(",".join(self._parse_csv_field(config.get("countries", ""))))  # Countries
            script_input.append("y")  # Confirmation
        else:
            # Most other scripts need: hscodes, countries (or just hscodes for some)
            if "hscodes" in config:
                script_input.append(",".join(self._parse_csv_field(config["hscodes"])))
            if "countries" in config:
                script_input.append(",".join(self._parse_csv_field(config["countries"])))
            elif "hscode" in config:  # Single hscode field
                script_input.append(",".join(self._parse_csv_field(config["hscode"])))
            
            # Add confirmation
            script_input.append("y")
        
        input_text = "\n".join(script_input) + "\n"
        
        return self._execute_script(script_path, input_text)
    
    def _run_programmatic_script(self, script_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run script in programmatic mode using environment variables"""
        logger.info(f"Running script in programmatic mode: {script_path}")
        logger.info(f"Config received: {config}")
        
        # Get the data-extractor directory as working directory
        service_dir = Path(__file__).parent.absolute()
        data_extractor_dir = service_dir.parent
        
        # Prepare environment variables
        env = os.environ.copy()
        env['PROGRAMMATIC_MODE'] = 'true'
        env['PAYLOAD_CONFIG'] = json.dumps(config)
        
        # Explicitly pass MongoDB credentials from environment
        # Load from .env if not already in environment
        if 'MONGO_URI' not in env or not env['MONGO_URI']:
            from dotenv import load_dotenv
            load_dotenv(data_extractor_dir / '.env')
            env['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://admin:Aaziko%21%40%23123@202.47.115.6:27017/?authSource=admin')
            env['MONGO_DB'] = os.getenv('MONGO_DB', 'Dhruval')
        
        logger.info(f"PAYLOAD_CONFIG being passed: {env['PAYLOAD_CONFIG']}")
        
        # Ensure PYTHONPATH includes the data-extractor directory
        current_pythonpath = env.get('PYTHONPATH', '')
        if str(data_extractor_dir) not in current_pythonpath:
            env['PYTHONPATH'] = f"{data_extractor_dir}:{current_pythonpath}" if current_pythonpath else str(data_extractor_dir)
        
        logger.info(f"Working directory: {data_extractor_dir}")
        logger.info(f"PYTHONPATH: {env.get('PYTHONPATH', 'NOT SET')}")
        logger.info(f"MONGO_URI: {env.get('MONGO_URI', 'NOT SET')[:50]}...")
        logger.info(f"MONGO_DB: {env.get('MONGO_DB', 'NOT SET')}")
        
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(data_extractor_dir),
            env=env,
            timeout=300  # 5 minute timeout
        )
        
        # Log stderr if there are any errors
        if result.stderr:
            logger.warning(f"Script stderr: {result.stderr[:500]}")
        
        if result.returncode == 0:
            # Parse output to extract number of payloads created
            output_text = result.stdout
            payload_count = 0
            
            import re
            
            # Remove all emojis and non-ASCII characters for easier parsing
            clean_output = re.sub(r'[^\x00-\x7F]+', '', output_text)
            
            # Debug logging
            logger.info(f"Parsing output for task count...")
            logger.info(f"Clean output sample: {clean_output[:500]}")
            
            # Priority 1: "New Payloads Inserted: X" - this is the actual count of inserted tasks
            match = re.search(r'New Payloads Inserted:\s*(\d+)', clean_output, re.IGNORECASE)
            if match:
                payload_count = int(match.group(1))
                logger.info(f"Found via 'New Payloads Inserted': {payload_count}")
            
            # Priority 2: "Inserted X new tasks" - alternative format
            if payload_count == 0:
                match = re.search(r'Inserted\s+(\d+)\s+new tasks', clean_output, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    logger.info(f"Found via 'Inserted X new tasks': {payload_count}")
            
            # Priority 3: "Final Database Size: X tasks" - fallback to total count
            if payload_count == 0:
                match = re.search(r'Final Database Size:\s*(\d+)\s*tasks', clean_output, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    logger.info(f"Found via 'Final Database Size': {payload_count}")
            
            logger.info(f"Final payload_count: {payload_count}")
            
            response = {
                "success": True,
                "message": "Payload generation completed successfully",
                "output": result.stdout,
                "script": script_path.name,
                "tasksCreated": payload_count,
                "payloadType": script_path.parent.name
            }
            logger.info(f"Returning response with tasksCreated={response['tasksCreated']}")
            return response
        else:
            return {
                "success": False,
                "message": f"Script execution failed with return code {result.returncode}",
                "output": result.stdout,
                "error": result.stderr,
                "script": script_path.name
            }
    
    def _execute_script(self, script_path: Path, input_text: str) -> Dict[str, Any]:
        """Execute the script with given input"""
        logger.info(f"Running script: {script_path}")
        logger.info(f"Input: {input_text}")
        
        # Get the data-extractor directory as working directory
        service_dir = Path(__file__).parent.absolute()
        data_extractor_dir = service_dir.parent
        
        result = subprocess.run(
            [sys.executable, str(script_path)],
            input=input_text,
            text=True,
            capture_output=True,
            cwd=str(data_extractor_dir),  # Use data-extractor directory as working directory
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            # Parse output to extract number of payloads created
            output_lines = result.stdout.split('\n')
            payload_count = 0
            
            import re
            
            # Try multiple patterns to extract task count
            for line in output_lines:
                # Pattern 1: "Total: X tasks"
                match = re.search(r'Total:\s*(\d+)\s+tasks?', line, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    continue
                
                # Pattern 2: "X tasks created"
                match = re.search(r'(\d+)\s+tasks?\s+created', line, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    continue
                
                # Pattern 3: "Created: X"
                match = re.search(r'Created:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    continue
                
                # Pattern 4: "Total combinations to create: X"
                match = re.search(r'Total combinations to create:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    continue
                
                # Pattern 5: "Combinations Processed: X"
                match = re.search(r'Combinations Processed:\s*(\d+)', line, re.IGNORECASE)
                if match:
                    payload_count = int(match.group(1))
                    continue
            
            return {
                "success": True,
                "message": "Payload generation completed successfully",
                "count": payload_count,
                "output": result.stdout,
                "script": str(script_path.name)
            }
        else:
            return {
                "success": False,
                "message": f"Script execution failed: {result.stderr}",
                "output": result.stdout,
                "error": result.stderr
            }
    
    def _create_trademap_tasks_directly(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create TradeMap tasks directly in MongoDB without using script"""
        import itertools
        from datetime import datetime
        from shared.task_creator_utils.mongodb_base import get_database
        
        try:
            # Get country1 and country2 from normalized config (exporting and importing)
            country1_val = config.get('country1', '')
            if isinstance(country1_val, str):
                country1_list = [c.strip() for c in country1_val.split(',') if c.strip()]
            else:
                country1_list = country1_val if country1_val else []
            
            country2_val = config.get('country2', '')
            if isinstance(country2_val, str):
                country2_list = [c.strip() for c in country2_val.split(',') if c.strip()]
            else:
                country2_list = country2_val if country2_val else []
            
            hscodes = config.get('hscodes', '')
            if isinstance(hscodes, str):
                hscodes_list = [h.strip() for h in hscodes.split(',') if h.strip()]
            else:
                hscodes_list = hscodes if hscodes else []
            
            # Get new scraping options
            time_series_types = config.get('time_series_types', ['yearly', 'quarterly', 'monthly'])
            view_types = config.get('view_types', ['by_country', 'by_product'])
            values_types = config.get('values_types', ['values'])
            
            # Handle "all" options
            all_hs_codes = config.get('all_hs_codes', False)
            all_exporting = config.get('all_exporting', False)
            all_importing = config.get('all_importing', False)
            
            # Load all countries from static/countries.json for expansion
            all_countries_list = []
            try:
                countries_file = Path(__file__).parent.parent / "static" / "countries.json"
                if countries_file.exists():
                    with open(countries_file, 'r', encoding='utf-8') as f:
                        countries_data = json.load(f)
                        all_countries_list = [c['Name'] for c in countries_data if c.get('Name')]
                    logger.info(f"Loaded {len(all_countries_list)} countries for expansion")
            except Exception as e:
                logger.warning(f"Failed to load countries for expansion: {e}")
            
            # If "all" is selected, expand to individual countries (not 'all' marker)
            if all_hs_codes or (hscodes_list and hscodes_list[0].lower() == 'all'):
                hscodes_list = ['all']  # HS codes still use 'all' marker
            
            # Expand exporting countries if all_exporting is True
            if all_exporting or (country1_list and country1_list[0].lower() == 'all'):
                if all_countries_list:
                    country1_list = all_countries_list
                    logger.info(f"Expanded all_exporting to {len(country1_list)} individual countries")
                else:
                    country1_list = ['all']  # Fallback if countries couldn't be loaded
            
            # Expand importing countries if all_importing is True
            if all_importing or (country2_list and country2_list[0].lower() == 'all'):
                if all_countries_list:
                    country2_list = all_countries_list
                    logger.info(f"Expanded all_importing to {len(country2_list)} individual countries")
                else:
                    country2_list = ['all']  # Fallback if countries couldn't be loaded
            
            # Create combinations: ONLY hscodes × country1 (exporting) × country2 (importing)
            # Pass time_series_types, view_types, values_types as LISTS to each task
            combinations = list(itertools.product(hscodes_list, country1_list, country2_list))
            # Insert tasks directly into MongoDB
            db = get_database()
            collection = db['scraper_tasks']
            
            tasks_to_insert = []
            # Track if we expanded countries (so we set flags to False for individual tasks)
            expanded_exporting = all_exporting and all_countries_list
            expanded_importing = all_importing and all_countries_list
            
            for hscode, c1, c2 in combinations:
                task = {
                    'scraper': 'trademap',
                    'status': 'pending',
                    'payload': {
                        'hscode': hscode,
                        'country1': c1,
                        'country2': c2,
                        'time_series_list': time_series_types,
                        'view_type_list': view_types,
                        'value_type_list': values_types,
                        'all_hs_codes': all_hs_codes,
                        # Set to False if we expanded to individual countries
                        'all_exporting': False if expanded_exporting else all_exporting,
                        'all_importing': False if expanded_importing else all_importing
                    },
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }
                tasks_to_insert.append(task)
            
            if tasks_to_insert:
                try:
                    result = collection.insert_many(tasks_to_insert, ordered=False)
                    inserted_count = len(result.inserted_ids)
                    logger.info(f"✅ Created {inserted_count} TradeMap tasks directly in MongoDB")
                    return {
                        "success": True,
                        "message": "Payload generation completed successfully",
                        "count": inserted_count,
                        "tasksCreated": inserted_count
                    }
                except Exception as insert_error:
                    if 'duplicate key error' in str(insert_error).lower():
                        logger.warning(f"Some duplicate tasks skipped")
                        inserted_count = len(tasks_to_insert)
                        return {
                            "success": True,
                            "message": "Payload generation completed",
                            "count": inserted_count,
                            "tasksCreated": inserted_count
                        }
                    else:
                        raise insert_error
            else:
                return {
                    "success": False,
                    "message": "No tasks to create"
                }
                
        except Exception as e:
            logger.error(f"Error creating TradeMap tasks directly: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def _create_macmap_tasks_directly(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create MacMap tariff tasks directly in MongoDB without using script"""
        import itertools
        from datetime import datetime
        from shared.task_creator_utils.mongodb_base import get_database
        
        try:
            # Get country1 and country2 from normalized config (importing and exporting)
            country1_val = config.get('country1', '')
            if isinstance(country1_val, str):
                country1_list = [c.strip() for c in country1_val.split(',') if c.strip()]
            else:
                country1_list = country1_val if country1_val else []
            
            country2_val = config.get('country2', '')
            if isinstance(country2_val, str):
                country2_list = [c.strip() for c in country2_val.split(',') if c.strip()]
            else:
                country2_list = country2_val if country2_val else []
            
            hscodes = config.get('hscodes', '')
            if isinstance(hscodes, str):
                hscodes_list = [h.strip() for h in hscodes.split(',') if h.strip()]
            else:
                hscodes_list = hscodes if hscodes else []
            
            year = config.get('year', 2025)
            if not isinstance(year, list):
                year = [year]
            
            # Create cartesian product: country1 (importing) x country2 (exporting) x hscodes x year
            combinations = list(itertools.product(country1_list, country2_list, hscodes_list, year))
            
            # Insert tasks directly into MongoDB
            db = get_database()
            collection = db['scraper_tasks']
            
            tasks_to_insert = []
            for country1, country2, hsc, yr in combinations:
                task = {
                    'scraper': 'MacMapTariff',
                    'status': 'pending',
                    'payload': {
                        'country1': country1,
                        'country2': country2,
                        'hsc': hsc,
                        'year': str(yr)
                    },
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }
                tasks_to_insert.append(task)
            
            if tasks_to_insert:
                # Use insert_many with ordered=False to continue on duplicates
                try:
                    result = collection.insert_many(tasks_to_insert, ordered=False)
                    inserted_count = len(result.inserted_ids)
                    logger.info(f"✅ Created {inserted_count} MacMap tasks directly in MongoDB")
                except Exception as insert_error:
                    # Handle duplicate key errors gracefully
                    if 'duplicate key error' in str(insert_error).lower():
                        # Count how many were actually inserted before the error
                        error_str = str(insert_error)
                        if 'nInserted' in error_str:
                            import re
                            match = re.search(r"'nInserted': (\d+)", error_str)
                            inserted_count = int(match.group(1)) if match else 0
                        else:
                            inserted_count = 0
                        
                        duplicate_count = len(tasks_to_insert) - inserted_count
                        logger.warning(f"⚠️ {duplicate_count} duplicate tasks skipped, {inserted_count} new tasks created")
                        
                        return {
                            "success": True,
                            "message": f"Payload generation completed. {inserted_count} new tasks created, {duplicate_count} duplicates skipped",
                            "count": inserted_count,
                            "tasksCreated": inserted_count,
                            "duplicates_skipped": duplicate_count
                        }
                    else:
                        raise insert_error
                
                return {
                    "success": True,
                    "message": "Payload generation completed successfully",
                    "count": inserted_count,
                    "tasksCreated": inserted_count
                }
            else:
                return {
                    "success": False,
                    "message": "No tasks to create"
                }
                
        except Exception as e:
            logger.error(f"Error creating MacMap tasks directly: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    def _parse_csv_field(self, value: Any) -> List[str]:
        """Parse CSV field value into list"""
        if isinstance(value, list):
            return value
        elif isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            return [str(value)] if isinstance(value, list) else [str(value)]
    
    def get_payload_statistics(self) -> Dict[str, Any]:
        """Get comprehensive payload statistics from all databases"""
        stats = {
            "total_payloads": 0,
            "database_files": 0,
            "last_generated": None,
            "by_type": {}
        }
        
        scrapped_data_dir = Path("shared/task_creator_utils/scrapped_data")
        if not scrapped_data_dir.exists():
            return stats
        
        db_files = list(scrapped_data_dir.glob("*.db"))
        stats["database_files"] = len(db_files)
        
        latest_timestamp = None
        
        for db_file in db_files:
            try:
                conn = sqlite3.connect(str(db_file))
                
                # Get total count
                total_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                stats["total_payloads"] += total_count
                
                # Get latest timestamp
                try:
                    latest_query = conn.execute(
                        "SELECT MAX(created_at) FROM tasks"
                    ).fetchone()[0]
                    
                    if latest_query:
                        if latest_timestamp is None or latest_query > latest_timestamp:
                            latest_timestamp = latest_query
                except:
                    pass
                
                # Store by type
                db_name = db_file.stem
                stats["by_type"][db_name] = {
                    "total": total_count,
                    "file": db_file.name
                }
                
                conn.close()
                
            except Exception as e:
                logger.error(f"Error reading database {db_file}: {e}")
                continue
        
        if latest_timestamp:
            stats["last_generated"] = latest_timestamp
        
        return stats
    
    def get_recent_generations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent payload generations across all databases"""
        recent_generations = []
        
        scrapped_data_dir = Path("shared/task_creator_utils/scrapped_data")
        if not scrapped_data_dir.exists():
            return recent_generations
        
        db_files = list(scrapped_data_dir.glob("*.db"))
        
        for db_file in db_files:
            try:
                conn = sqlite3.connect(str(db_file))
                
                # Get recent records
                records = conn.execute("""
                    SELECT created_at, COUNT(*) as count
                    FROM tasks 
                    WHERE created_at IS NOT NULL
                    GROUP BY DATE(created_at)
                    ORDER BY created_at DESC 
                    LIMIT ?
                """, (limit,)).fetchall()
                
                for record in records:
                    recent_generations.append({
                        "date": record[0],
                        "count": record[1],
                        "database": db_file.stem
                    })
                
                conn.close()
                
            except Exception as e:
                logger.error(f"Error reading recent generations from {db_file}: {e}")
                continue
        
        # Sort by date and limit
        recent_generations.sort(key=lambda x: x["date"], reverse=True)
        return recent_generations[:limit]

# Global instance
payload_service = PayloadService() 