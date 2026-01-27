#!/usr/bin/env python3
"""
EximPedia Payload Creator - MongoDB Version
Supports programmatic mode for API integration
"""
import sys
import os
import json

script_dir = os.path.dirname(os.path.abspath(__file__))
data_extractor_dir = os.path.dirname(os.path.dirname(script_dir))
if data_extractor_dir not in sys.path:
    sys.path.insert(0, data_extractor_dir)

from shared.task_creator_utils.base_payload_creator import BasePayloadCreator

ENDPOINT = "http://0.0.0.0:1080/api/v1/scrape/eximpedia"

FIELD_PROMPTS = {
    'start_date': 'Start Date (MM/DD/YYYY)',
    'end_date': 'End Date (MM/DD/YYYY)',
    'hscode': 'HS Codes',
    'country': 'Countries',
    'mode': 'Mode (import/export)'
}

class EximPediaPayloadCreator(BasePayloadCreator):
    """Extended payload creator for EximPedia with date handling"""
    
    def create_payloads_from_params(self, **params):
        """Override to split date ranges into 15-day chunks"""
        import time
        import itertools
        from datetime import datetime, timedelta
        
        # Split date ranges into 15-day chunks and create paired date ranges
        if 'start_date' in params and 'end_date' in params:
            start_dates = params.get('start_date', [])
            end_dates = params.get('end_date', [])
            
            # Ensure they are lists
            if not isinstance(start_dates, list):
                start_dates = [start_dates]
            if not isinstance(end_dates, list):
                end_dates = [end_dates]
            
            # Generate 15-day chunks for each start/end date pair
            chunked_date_pairs = []
            
            for start_date_str, end_date_str in zip(start_dates, end_dates):
                try:
                    # Parse dates - try multiple formats
                    start_date = None
                    end_date = None
                    
                    # Try parsing with leading zeros first
                    for fmt in ['%m/%d/%Y', '%-m/%-d/%Y', '%d/%m/%Y', '%-d/%-m/%Y']:
                        try:
                            start_date = datetime.strptime(start_date_str, fmt)
                            break
                        except:
                            continue
                    
                    # If still not parsed, try manual parsing (M/D/YYYY format)
                    if start_date is None:
                        parts = start_date_str.split('/')
                        if len(parts) == 3:
                            start_date = datetime(int(parts[2]), int(parts[0]), int(parts[1]))
                    
                    # Parse end date
                    for fmt in ['%m/%d/%Y', '%-m/%-d/%Y', '%d/%m/%Y', '%-d/%-m/%Y']:
                        try:
                            end_date = datetime.strptime(end_date_str, fmt)
                            break
                        except:
                            continue
                    
                    # If still not parsed, try manual parsing (M/D/YYYY format)
                    if end_date is None:
                        parts = end_date_str.split('/')
                        if len(parts) == 3:
                            end_date = datetime(int(parts[2]), int(parts[0]), int(parts[1]))
                    
                    if start_date is None or end_date is None:
                        raise ValueError(f"Could not parse dates: {start_date_str}, {end_date_str}")
                    
                    print(f"🔍 DEBUG: Parsed dates - start: {start_date}, end: {end_date}")
                    
                    # Get chunk_days from params, default to 90
                    chunk_days = int(params.get('chunk_days', [90])[0]) if isinstance(params.get('chunk_days'), list) else int(params.get('chunk_days', 90))
                    print(f"🔍 DEBUG: Using chunk size: {chunk_days} days")
                    
                    # Generate chunks based on user-specified chunk_days
                    current_start = start_date
                    chunk_count = 0
                    while current_start <= end_date:
                        # Calculate remaining days
                        remaining_days = (end_date - current_start).days + 1
                        
                        # Always use end_date for last chunk to avoid tiny chunks
                        # Use chunk_days for intermediate chunks
                        if remaining_days <= chunk_days:
                            chunk_end = end_date
                        else:
                            # chunk_days-1 because we include both start and end dates
                            chunk_end = current_start + timedelta(days=chunk_days-1)
                        
                        # Format dates with leading zeros: MM/DD/YYYY (required by scraper)
                        start_formatted = current_start.strftime('%m/%d/%Y')
                        end_formatted = chunk_end.strftime('%m/%d/%Y')
                        
                        actual_days = (chunk_end - current_start).days + 1
                        chunk_count += 1
                        print(f"📅 Chunk {chunk_count}: {start_formatted} to {end_formatted} ({actual_days} days)")
                        
                        # Add as a paired tuple
                        chunked_date_pairs.append((start_formatted, end_formatted))
                        
                        # Move to next chunk (start from day after chunk_end)
                        current_start = chunk_end + timedelta(days=1)
                    
                    print(f"✅ {chunk_count} chunks created using {chunk_days}-day chunks")
                        
                except Exception as e:
                    print(f"⚠️  Error parsing dates {start_date_str} to {end_date_str}: {e}")
                    import traceback
                    traceback.print_exc()
                    # If parsing fails, use original dates as a pair
                    chunked_date_pairs.append((start_date_str, end_date_str))
            
            # Remove start_date and end_date from params temporarily
            params.pop('start_date', None)
            params.pop('end_date', None)
        else:
            chunked_date_pairs = []
        
        # Ensure all other fields are lists (except email and password which are single values)
        for field in self.unique_fields:
            if field not in ['start_date', 'end_date', 'email', 'password'] and field in params:
                if not isinstance(params[field], list):
                    params[field] = [params[field]]
        
        # Store email and password separately (they're not list fields)
        email = params.pop('email', 'aazikodevmern25@gmail.com')
        password = params.pop('password', 'Aaziko@123')
        
        # Call parent method with modified logic
        start_time = time.time()
        
        self.print_header(f"🚀 {self.scraper_name} Payload Creation")
        
        # Calculate total combinations (date pairs count as 1 combination)
        total_combinations = len(chunked_date_pairs) if chunked_date_pairs else 1
        for field in self.unique_fields:
            if field not in ['start_date', 'end_date']:
                field_values = params.get(field, [])
                total_combinations *= len(field_values)
                print(f"{field.replace('_', ' ').title()}: {len(field_values)} selected")
        
        print(f"Date Ranges: {len(chunked_date_pairs)} chunks")
        print(f"Total combinations: {total_combinations:,}")
        
        # Prepare batch insert data
        payloads_batch = []
        processed_count = 0
        inserted_count = 0
        
        print(f"\n📊 Processing {total_combinations:,} combinations...")
        
        # Generate all combinations for non-date fields
        non_date_fields = [f for f in self.unique_fields if f not in ['start_date', 'end_date']]
        field_values_list = []
        for field in non_date_fields:
            values = params.get(field, [])
            field_values_list.append(values)
        
        # Generate combinations
        for non_date_combo in itertools.product(*field_values_list):
            # For each non-date combination, create payloads for all date pairs
            for start_date, end_date in chunked_date_pairs:
                # Build complete payload with date pair
                payload = {}
                for i, field in enumerate(non_date_fields):
                    payload[field] = non_date_combo[i]
                payload['start_date'] = start_date
                payload['end_date'] = end_date
                payload['email'] = email
                payload['password'] = password
                
                payloads_batch.append(payload)
                processed_count += 1
                
                # Batch insert every BATCH_SIZE records
                if len(payloads_batch) >= self.batch_size:
                    try:
                        inserted = self.batch_insert_payloads(payloads_batch)
                        inserted_count += inserted
                        
                        elapsed = time.time() - start_time
                        rate = processed_count / elapsed if elapsed > 0 else 0
                        eta = (total_combinations - processed_count) / rate if rate > 0 else 0
                        progress = (processed_count / total_combinations) * 100
                        
                        if inserted > 0:
                            print(f"📊 Progress: {processed_count:,}/{total_combinations:,} ({progress:.1f}%) | "
                                  f"Inserted: {inserted} | Rate: {rate:.0f}/s | ETA: {eta:.0f}s")
                        
                        payloads_batch = []
                    except Exception as e:
                        print(f"❌ Error inserting batch: {e}")
                        raise
        
        # Insert remaining payloads
        if payloads_batch:
            try:
                inserted = self.batch_insert_payloads(payloads_batch)
                inserted_count += inserted
                if inserted > 0:
                    print(f"📊 Inserted final batch of {inserted} payloads")
            except Exception as e:
                print(f"❌ Error inserting final batch: {e}")
        
        # Performance summary
        processing_time = time.time() - start_time
        
        self.print_header(f"🎉 {self.scraper_name} Payload Creation Complete")
        
        final_stats = self.get_database_stats()
        self.print_stats(final_stats, f"Final {self.scraper_name} Results")
        
        print(f"\n⚡ Performance Summary:")
        print(f"   ⏱️  Total Processing Time: {processing_time:.1f} seconds")
        print(f"   🚀 Combinations Processed: {processed_count:,}")
        print(f"   ✅ New Payloads Inserted: {inserted_count:,}")
        if processing_time > 0:
            print(f"   💻 Processing Rate: {processed_count/processing_time:.0f} combinations/second")
        print(f"   📊 Final Database Size: {final_stats.get('total_tasks', 0):,} tasks")

if __name__ == "__main__":
    # Check for programmatic mode
    if os.environ.get('PROGRAMMATIC_MODE') == 'true':
        try:
            config = json.loads(os.environ.get('PAYLOAD_CONFIG', '{}'))
            
            print(f"🔍 DEBUG: Received config: {config}")
            
            creator = EximPediaPayloadCreator(
                scraper_id='eximpedia',
                scraper_name='eximpedia',
                unique_fields=['start_date', 'end_date', 'hscode', 'country', 'mode'],
                endpoint=ENDPOINT
            )
            
            # Prepare params from config - dates are already in correct format
            params = {}
            
            # Handle hscodes - support both 'hscode' and 'hscodes', split comma-separated
            hscodes_raw = config.get('hscode') or config.get('hscodes')
            if hscodes_raw:
                if isinstance(hscodes_raw, str):
                    # Split comma-separated HS codes into individual items
                    params['hscode'] = [h.strip() for h in hscodes_raw.split(',')]
                elif isinstance(hscodes_raw, list):
                    params['hscode'] = hscodes_raw
            
            # Handle countries - support both 'country' and 'countries', split comma-separated
            countries_raw = config.get('country') or config.get('countries')
            if countries_raw:
                if isinstance(countries_raw, str):
                    params['country'] = [c.strip() for c in countries_raw.split(',')]
                else:
                    params['country'] = countries_raw
            
            # Handle mode
            if 'mode' in config:
                params['mode'] = [config['mode']] if isinstance(config['mode'], str) else config['mode']
            
            # Handle dates directly (no conversion needed)
            if 'start_date' in config:
                params['start_date'] = [config['start_date']] if isinstance(config['start_date'], str) else config['start_date']
            
            if 'end_date' in config:
                params['end_date'] = [config['end_date']] if isinstance(config['end_date'], str) else config['end_date']
            
            # Handle chunk_days - pass user's specified chunk size
            if 'chunk_days' in config:
                params['chunk_days'] = config['chunk_days']
            
            # Handle email and password
            if 'email' in config:
                params['email'] = config['email']
            if 'password' in config:
                params['password'] = config['password']
            
            print(f"🔍 DEBUG: Prepared params: {params}")
            
            creator.create_payloads_from_params(**params)
            
        except Exception as e:
            print(f"❌ Error in programmatic mode: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Interactive mode
        creator = EximPediaPayloadCreator(
            scraper_id='eximpedia',
            scraper_name='eximpedia',
            unique_fields=['start_date', 'end_date', 'hscode', 'country', 'mode'],
            endpoint=ENDPOINT
        )
        creator.run_interactive(FIELD_PROMPTS)

