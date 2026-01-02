#!/usr/bin/env python3
"""
Country Code Mapper Service
Converts country codes (ISO 2/3) to full country names
"""
import json
import os
from pathlib import Path
from typing import Dict, Optional

class CountryMapper:
    """Service to map country codes to full names"""
    
    def __init__(self):
        self.code_to_name: Dict[str, str] = {}
        self._load_mappings()
    
    def _load_mappings(self):
        """Load country mappings from JSON files"""
        try:
            # Get the data-extractor directory
            current_dir = Path(__file__).parent.parent
            
            # Load MacMap countries (PRIORITY - most accurate for MacMap scrapers)
            macmap_file = current_dir / "scrapers" / "macmap" / "macmap_countries" / "countries.json"
            if macmap_file.exists():
                with open(macmap_file, 'r', encoding='utf-8') as f:
                    macmap_countries = json.load(f)
                    for country in macmap_countries:
                        iso2 = country.get('ISO2', '').upper()
                        iso3 = country.get('ISO3', '').upper()
                        name = country.get('Name', '')
                        
                        if iso3 and name:
                            self.code_to_name[iso3] = name
                        if iso2 and name:
                            self.code_to_name[iso2] = name
            
            # Load import countries (fallback)
            imp_file = current_dir / "payloads" / "imp_ex_countries.json"
            if imp_file.exists():
                with open(imp_file, 'r', encoding='utf-8') as f:
                    imp_data = json.load(f)
                    for country in imp_data.get('data', {}).get('countries', []):
                        code_iso_3 = country.get('code_iso_3', '').upper()
                        code_iso_2 = country.get('code_iso_2', '').upper()
                        name = country.get('country', '')
                        
                        # Only add if not already present from MacMap
                        if code_iso_3 and name and code_iso_3 not in self.code_to_name:
                            self.code_to_name[code_iso_3] = name
                        if code_iso_2 and name and code_iso_2 not in self.code_to_name:
                            self.code_to_name[code_iso_2] = name
            
            # Load export countries (fallback)
            exp_file = current_dir / "payloads" / "exp_ex_countries.json"
            if exp_file.exists():
                with open(exp_file, 'r', encoding='utf-8') as f:
                    exp_data = json.load(f)
                    for country in exp_data.get('data', {}).get('countries', []):
                        code_iso_3 = country.get('code_iso_3', '').upper()
                        code_iso_2 = country.get('code_iso_2', '').upper()
                        name = country.get('country', '')
                        
                        # Only add if not already present from MacMap
                        if code_iso_3 and name and code_iso_3 not in self.code_to_name:
                            self.code_to_name[code_iso_3] = name
                        if code_iso_2 and name and code_iso_2 not in self.code_to_name:
                            self.code_to_name[code_iso_2] = name
            
            # Add common mappings that might be missing
            common_mappings = {
                'USA': 'United States',
                'US': 'United States',
                'UK': 'United Kingdom',
                'GB': 'United Kingdom',
                'GBR': 'United Kingdom',
                'CHN': 'China',
                'CN': 'China',
                'IND': 'India',
                'IN': 'India',
                'JPN': 'Japan',
                'JP': 'Japan',
                'DEU': 'Germany',
                'DE': 'Germany',
                'FRA': 'France',
                'FR': 'France',
                'ITA': 'Italy',
                'IT': 'Italy',
                'ESP': 'Spain',
                'ES': 'Spain',
                'CAN': 'Canada',
                'CA': 'Canada',
                'AUS': 'Australia',
                'AU': 'Australia',
                'BRA': 'Brazil',
                'BR': 'Brazil',
                'MEX': 'Mexico',
                'MX': 'Mexico',
                'RUS': 'Russia',
                'RU': 'Russia',
                'KOR': 'South Korea',
                'KR': 'South Korea',
                'SAU': 'Saudi Arabia',
                'SA': 'Saudi Arabia',
                'ARE': 'United Arab Emirates',
                'AE': 'United Arab Emirates',
                'TUR': 'Turkey',
                'TR': 'Turkey',
                'POL': 'Poland',
                'PL': 'Poland',
                'NLD': 'Netherlands',
                'NL': 'Netherlands',
                'BEL': 'Belgium',
                'BE': 'Belgium',
                'SWE': 'Sweden',
                'SE': 'Sweden',
                'CHE': 'Switzerland',
                'CH': 'Switzerland',
                'NOR': 'Norway',
                'NO': 'Norway',
                'DNK': 'Denmark',
                'DK': 'Denmark',
                'FIN': 'Finland',
                'FI': 'Finland',
                'AUT': 'Austria',
                'AT': 'Austria',
                'PRT': 'Portugal',
                'PT': 'Portugal',
                'GRC': 'Greece',
                'GR': 'Greece',
                'CZE': 'Czech Republic',
                'CZ': 'Czech Republic',
                'HUN': 'Hungary',
                'HU': 'Hungary',
                'ROU': 'Romania',
                'RO': 'Romania',
                'BGR': 'Bulgaria',
                'BG': 'Bulgaria',
                'HRV': 'Croatia',
                'HR': 'Croatia',
                'SVK': 'Slovakia',
                'SK': 'Slovakia',
                'SVN': 'Slovenia',
                'SI': 'Slovenia',
                'LTU': 'Lithuania',
                'LT': 'Lithuania',
                'LVA': 'Latvia',
                'LV': 'Latvia',
                'EST': 'Estonia',
                'EE': 'Estonia',
                'IRL': 'Ireland',
                'IE': 'Ireland',
                'ZAF': 'South Africa',
                'ZA': 'South Africa',
                'EGY': 'Egypt',
                'EG': 'Egypt',
                'NGA': 'Nigeria',
                'NG': 'Nigeria',
                'KEN': 'Kenya',
                'KE': 'Kenya',
                'THA': 'Thailand',
                'TH': 'Thailand',
                'VNM': 'Vietnam',
                'VN': 'Vietnam',
                'MYS': 'Malaysia',
                'MY': 'Malaysia',
                'SGP': 'Singapore',
                'SG': 'Singapore',
                'IDN': 'Indonesia',
                'ID': 'Indonesia',
                'PHL': 'Philippines',
                'PH': 'Philippines',
                'PAK': 'Pakistan',
                'PK': 'Pakistan',
                'BGD': 'Bangladesh',
                'BD': 'Bangladesh',
                'ARG': 'Argentina',
                'AR': 'Argentina',
                'CHL': 'Chile',
                'CL': 'Chile',
                'COL': 'Colombia',
                'CO': 'Colombia',
                'PER': 'Peru',
                'PE': 'Peru',
                'VEN': 'Venezuela',
                'VE': 'Venezuela',
                'NZL': 'New Zealand',
                'NZ': 'New Zealand',
                'ISR': 'Israel',
                'IL': 'Israel',
                'IRN': 'Iran',
                'IR': 'Iran',
                'IRQ': 'Iraq',
                'IQ': 'Iraq',
                'QAT': 'Qatar',
                'QA': 'Qatar',
                'KWT': 'Kuwait',
                'KW': 'Kuwait',
                'OMN': 'Oman',
                'OM': 'Oman',
                'JOR': 'Jordan',
                'JO': 'Jordan',
                'LBN': 'Lebanon',
                'LB': 'Lebanon',
                'MAR': 'Morocco',
                'MA': 'Morocco',
                'DZA': 'Algeria',
                'DZ': 'Algeria',
                'TUN': 'Tunisia',
                'TN': 'Tunisia',
                'LBY': 'Libya',
                'LY': 'Libya',
                'UKR': 'Ukraine',
                'UA': 'Ukraine',
            }
            
            # Add common mappings (only for codes not in MacMap)
            for code, name in common_mappings.items():
                if code not in self.code_to_name:
                    self.code_to_name[code] = name
            
            print(f"✅ Country mapper loaded {len(self.code_to_name)} country code mappings")
            
        except Exception as e:
            print(f"⚠️  Error loading country mappings: {e}")
    
    def get_country_name(self, code: str) -> str:
        """
        Convert country code to full name
        
        Args:
            code: Country code (ISO 2 or ISO 3)
            
        Returns:
            Full country name, or the original code if not found
        """
        if not code:
            return code
        
        # Try uppercase
        code_upper = code.upper().strip()
        if code_upper in self.code_to_name:
            return self.code_to_name[code_upper]
        
        # If already a full name (contains spaces or is long), return as is
        if ' ' in code or len(code) > 3:
            return code
        
        # Not found, return original
        return code
    
    def convert_country_list(self, countries: str) -> str:
        """
        Convert comma-separated country codes to full names
        
        Args:
            countries: Comma-separated country codes
            
        Returns:
            Comma-separated full country names
        """
        if not countries:
            return countries
        
        codes = [c.strip() for c in countries.split(',')]
        names = [self.get_country_name(code) for code in codes]
        return ','.join(names)


# Global instance
country_mapper = CountryMapper()
