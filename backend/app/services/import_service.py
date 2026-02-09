
import pandas as pd
from datetime import datetime
from app import db
from app.models import TimelineEvent, CompromisedHost, CompromisedAccount, NetworkIndicator, MalwareTool, HostBasedIndicator
from app.services.encryption_service import encryption_service

class ImportService:
    @staticmethod
    def parse_excel(file):
        """Parse Excel file and return raw data structure."""
        try:
            xls = pd.ExcelFile(file)
            sheets_data = []

            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name)
                
                # Replace NaT and NaN with None (null in JSON)
                # First convert to object to allow mixed types (None in numeric/datetime columns)
                df = df.astype(object)
                df = df.where(pd.notnull(df), None)
                
                # Double check for NaT specifically as it can persist
                df = df.replace({pd.NaT: None})
                
                # Get headers
                headers = list(df.columns)
                
                # Get rows as list of dicts
                rows = df.to_dict(orient='records')
                
                sheets_data.append({
                    'name': sheet_name,
                    'headers': headers,
                    'rows': rows
                })
                
            return {'sheets': sheets_data}
        except Exception as e:
            raise ValueError(f"Failed to parse Excel: {str(e)}")

    @staticmethod
    def bulk_create_entities(incident_id, data, user_id):
        """Bulk create entities from normalized JSON data."""
        results = {
            'timeline_events': 0,
            'hosts': 0,
            'accounts': 0,
            'network_iocs': 0,
            'host_iocs': 0,
            'malware': 0
        }
        
        try:
            if 'timeline_events' in data:
                results['timeline_events'] = ImportService._create_timeline_events(incident_id, data['timeline_events'], user_id)
            
            if 'hosts' in data:
                results['hosts'] = ImportService._create_hosts(incident_id, data['hosts'], user_id)
                
            if 'accounts' in data:
                results['accounts'] = ImportService._create_accounts(incident_id, data['accounts'], user_id)
                
            if 'network_iocs' in data:
                results['network_iocs'] = ImportService._create_network_iocs(incident_id, data['network_iocs'], user_id)
                
            if 'malware' in data:
                results['malware'] = ImportService._create_malware(incident_id, data['malware'], user_id)
                
            if 'host_iocs' in data:
                results['host_iocs'] = ImportService._create_host_iocs(incident_id, data['host_iocs'], user_id)
                
            db.session.commit()
            return results
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to import data: {str(e)}")

    @staticmethod
    def process_excel_import(incident_id, file, user_id):
        """Process Excel file import for an incident."""
        try:
            xls = pd.ExcelFile(file)
            
            results = {
                'timeline_events': 0,
                'hosts': 0,
                'accounts': 0,
                'network_iocs': 0,
                'host_iocs': 0,
                'malware': 0
            }
            
            # Process sheets
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name)
                lower_sheet = sheet_name.lower()
                
                if 'timeline' in lower_sheet:
                    results['timeline_events'] += ImportService._import_timeline(incident_id, df, user_id)
                elif 'host' in lower_sheet and 'account' not in lower_sheet and 'ioc' not in lower_sheet:
                    results['hosts'] += ImportService._import_hosts(incident_id, df, user_id)
                elif 'account' in lower_sheet:
                    results['accounts'] += ImportService._import_accounts(incident_id, df, user_id)
                elif 'network' in lower_sheet:
                    results['network_iocs'] += ImportService._import_network_iocs(incident_id, df, user_id)
                elif 'malware' in lower_sheet or 'tool' in lower_sheet:
                    results['malware'] += ImportService._import_malware(incident_id, df, user_id)
                elif 'host' in lower_sheet and 'ioc' in lower_sheet:
                    results['host_iocs'] += ImportService._import_host_iocs(incident_id, df, user_id)
            
            db.session.commit()
            return results
            
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to process import: {str(e)}")

    @staticmethod
    def _clean_df(df):
        """Clean dataframe columns and values."""
        # Normalize column names: lowercase, strip whitespace, replace spaces with underscores
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        # Drop empty rows
        df = df.dropna(how='all')
        # Replace NaN with None
        df = df.where(pd.notnull(df), None)
        return df

    @staticmethod
    def _parse_date(date_val):
        """Parse date string or object."""
        if not date_val:
            return datetime.now()
        
        if isinstance(date_val, str):
            try:
                # Try common formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%m/%d/%Y %H:%M', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(date_val, fmt)
                    except ValueError:
                        continue
            except:
                pass
        
        if hasattr(date_val, 'to_pydatetime'):
            return date_val.to_pydatetime()
            
        return date_val if isinstance(date_val, datetime) else datetime.now()

    @staticmethod
    def _import_timeline(incident_id, df, user_id):
        """Import timeline events from a cleaned spreadsheet dataframe."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            if not row.get('activity') and not row.get('description'):
                continue
                
            event = TimelineEvent(
                incident_id=incident_id,
                timestamp=ImportService._parse_date(row.get('timestamp') or row.get('date') or row.get('time')),
                activity=row.get('activity') or row.get('description'),
                hostname=row.get('host') or row.get('hostname') or row.get('system'),
                source=row.get('source'),
                mitre_tactic=row.get('tactic') or row.get('mitre_tactic'),
                mitre_technique=row.get('technique_id') or row.get('technique') or row.get('mitre_technique'),
                created_by=user_id
            )
            db.session.add(event)
            count += 1
            
        return count

    @staticmethod
    def _import_hosts(incident_id, df, user_id):
        """Import compromised hosts from a cleaned spreadsheet dataframe, skipping duplicates."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            hostname = row.get('hostname') or row.get('host') or row.get('system_name')
            if not hostname:
                continue
                
            # Check for existing
            existing = CompromisedHost.query.filter_by(incident_id=incident_id, hostname=hostname).first()
            if existing:
                continue
                
            host = CompromisedHost(
                incident_id=incident_id,
                hostname=hostname,
                ip_address=row.get('ip_address') or row.get('ip'),
                system_type=row.get('type') or row.get('system_type') or 'workstation',
                os_version=row.get('os') or row.get('os_version'),
                evidence=row.get('evidence') or row.get('reason'),
                first_seen=ImportService._parse_date(row.get('first_seen')),
                containment_status=row.get('status') or 'active',
                created_by=user_id
            )
            db.session.add(host)
            count += 1
            
        return count

    @staticmethod
    def _import_accounts(incident_id, df, user_id):
        """Import compromised accounts from a cleaned spreadsheet dataframe, encrypting passwords."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            account_name = row.get('account_name') or row.get('account') or row.get('username')
            if not account_name:
                continue
                
            pwd = row.get('password')
            enc_pwd = encryption_service.encrypt(pwd) if pwd else None
                
            account = CompromisedAccount(
                incident_id=incident_id,
                account_name=account_name,
                datetime_seen=ImportService._parse_date(row.get('timestamp') or row.get('date')),
                password_encrypted=enc_pwd,
                host_system=row.get('host') or row.get('system') or row.get('hostname'),
                account_type=row.get('type') or 'other',
                domain=row.get('domain'),
                is_privileged=str(row.get('privileged')).lower() in ['true', 'yes', '1'],
                created_by=user_id
            )
            db.session.add(account)
            count += 1
            
        return count
    
    @staticmethod
    def _import_network_iocs(incident_id, df, user_id):
        """Import network IOCs from a cleaned spreadsheet dataframe."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            value = row.get('value') or row.get('ip') or row.get('domain') or row.get('url') or row.get('dns_ip')
            if not value:
                continue
                
            ioc = NetworkIndicator(
                incident_id=incident_id,
                dns_ip=value,
                timestamp=ImportService._parse_date(row.get('timestamp') or row.get('date')),
                protocol=row.get('protocol'),
                port=int(row.get('port')) if row.get('port') else None,
                direction=row.get('direction') or 'outbound',
                description=row.get('description'),
                is_malicious=True,
                created_by=user_id
            )
            db.session.add(ioc)
            count += 1
        return count
        
    @staticmethod
    def _import_malware(incident_id, df, user_id):
        """Import malware and tools from a cleaned spreadsheet dataframe."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            name = row.get('name') or row.get('file_name') or row.get('tool_name')
            if not name:
                continue
                
            malware = MalwareTool(
                incident_id=incident_id,
                file_name=name,
                type=row.get('type') or 'malware',
                hash=row.get('hash') or row.get('sha256') or row.get('md5'),
                path=row.get('path') or row.get('file_path'),
                description=row.get('description'),
                created_by=user_id
            )
            db.session.add(malware)
            count += 1
        return count
        
    @staticmethod
    def _import_host_iocs(incident_id, df, user_id):
        """Import host-based IOCs from a cleaned spreadsheet dataframe."""
        df = ImportService._clean_df(df)
        count = 0
        
        for _, row in df.iterrows():
            artifact = row.get('artifact') or row.get('indicator') or row.get('value')
            if not artifact:
                continue
                
            ioc = HostBasedIndicator(
                incident_id=incident_id,
                type=row.get('type') or 'other',
                value=artifact,
                hostname=row.get('hostname') or row.get('host'),
                path=row.get('path'),
                description=row.get('description'),
                created_by=user_id
            )
            db.session.add(ioc)
            count += 1
        return count

    @staticmethod
    def _clean_kwargs(model_class, **kwargs):
        """Filter kwargs to only include valid columns for the model."""
        valid_columns = {c.key for c in model_class.__table__.columns}
        return {k: v for k, v in kwargs.items() if k in valid_columns}

    @staticmethod
    def _create_timeline_events(incident_id, items, user_id):
        """Create timeline event records from normalized JSON items."""
        count = 0
        for item in items:
            if not item.get('activity'):
                continue
            
            kwargs = {
                'incident_id': incident_id,
                'timestamp': ImportService._parse_date(item.get('timestamp')),
                'activity': item.get('activity'),
                'hostname': item.get('hostname'),
                'source': item.get('source'),
                'mitre_tactic': item.get('mitre_tactic'),
                'mitre_technique': item.get('mitre_technique'),
                'created_by': user_id
            }
            # Clean and create
            valid_kwargs = ImportService._clean_kwargs(TimelineEvent, **kwargs)
            event = TimelineEvent(**valid_kwargs)
            db.session.add(event)
            count += 1
        return count

    @staticmethod
    def _create_hosts(incident_id, items, user_id):
        """Create compromised host records from normalized JSON items, skipping duplicates."""
        count = 0
        for item in items:
            hostname = item.get('hostname')
            if not hostname:
                continue
            
            existing = CompromisedHost.query.filter_by(incident_id=incident_id, hostname=hostname).first()
            if existing:
                continue
                
            kwargs = {
                'incident_id': incident_id,
                'hostname': hostname,
                'ip_address': item.get('ip_address'),
                'system_type': item.get('system_type') or 'workstation',
                'os_version': item.get('os_version'),
                'evidence': item.get('evidence'),
                'first_seen': ImportService._parse_date(item.get('first_seen')),
                'containment_status': item.get('containment_status') or 'active',
                'created_by': user_id
            }
            valid_kwargs = ImportService._clean_kwargs(CompromisedHost, **kwargs)
            host = CompromisedHost(**valid_kwargs)
            db.session.add(host)
            count += 1
        return count

    @staticmethod
    def _create_accounts(incident_id, items, user_id):
        """Create compromised account records from normalized JSON items with type normalization and password encryption."""
        count = 0
        valid_types = CompromisedAccount.ACCOUNT_TYPES
        
        for item in items:
            account_name = item.get('account_name')
            if not account_name:
                continue
                
            pwd = item.get('password')
            enc_pwd = encryption_service.encrypt(pwd) if pwd else None
            
            # Normalize account type
            raw_type = str(item.get('account_type') or 'other').lower().strip()
            account_type = 'other'
            
            if raw_type in valid_types:
                account_type = raw_type
            else:
                # Fuzzy matching
                if 'domain' in raw_type:
                    account_type = 'domain'
                elif 'local' in raw_type:
                    account_type = 'local'
                elif 'ftp' in raw_type:
                    account_type = 'ftp'
                elif 'service' in raw_type:
                    account_type = 'service'
                elif 'app' in raw_type or 'web' in raw_type:
                    account_type = 'application'
                elif 'admin' in raw_type or 'root' in raw_type:
                    account_type = 'admin'
                
            kwargs = {
                'incident_id': incident_id,
                'account_name': account_name,
                'datetime_seen': ImportService._parse_date(item.get('datetime_seen') or item.get('timestamp')),
                'password_encrypted': enc_pwd,
                'host_system': item.get('host_system'),
                'account_type': account_type,
                'domain': item.get('domain'),
                'sid': item.get('sid'),
                'is_privileged': str(item.get('is_privileged')).lower() in ['true', 'yes', '1'],
                'created_by': user_id
            }
            valid_kwargs = ImportService._clean_kwargs(CompromisedAccount, **kwargs)
            account = CompromisedAccount(**valid_kwargs)
            db.session.add(account)
            count += 1
        return count

    @staticmethod
    def _create_network_iocs(incident_id, items, user_id):
        """Create network indicator records from normalized JSON items."""
        count = 0
        for item in items:
            value = item.get('dns_ip')
            if not value:
                continue
                
            kwargs = {
                'incident_id': incident_id,
                'dns_ip': value,
                'timestamp': ImportService._parse_date(item.get('timestamp')),
                'protocol': item.get('protocol'),
                'port': int(item.get('port')) if item.get('port') else None,
                'direction': item.get('direction') or 'outbound',
                'description': item.get('description'),
                'source_host': item.get('source_host'),
                'is_malicious': True,
                'created_by': user_id
            }
            valid_kwargs = ImportService._clean_kwargs(NetworkIndicator, **kwargs)
            ioc = NetworkIndicator(**valid_kwargs)
            db.session.add(ioc)
            count += 1
        return count

    @staticmethod
    def _parse_size(size_val):
        """Parse file size string to bytes (integer)."""
        if not size_val:
            return None
            
        if isinstance(size_val, (int, float)):
            return int(size_val)
            
        # Try to extract first number found
        import re
        s = str(size_val).upper().replace(',', '')
        match = re.search(r'(\d+(\.\d+)?)', s)
        if not match:
            return None
            
        val = float(match.group(1))
        
        # Simple unit handling
        if 'KB' in s:
            val *= 1024
        elif 'MB' in s:
            val *= 1024 * 1024
        elif 'GB' in s:
            val *= 1024 * 1024 * 1024
        elif 'TB' in s:
            val *= 1024 * 1024 * 1024 * 1024
            
        return int(val)

    @staticmethod
    def _clean_malware_fields(item):
        """Helper to prepare malware fields."""
        # Determine if tool based on is_tool field or guess from description/type
        is_tool_val = item.get('is_tool')
        is_tool = False
        if is_tool_val:
            is_tool = str(is_tool_val).lower() in ['true', 'yes', '1']
        
        # If "type" was passed, and it says tool, we can use that too
        if str(item.get('type')).lower() == 'tool':
            is_tool = True
            
        # Handle hash auto-detection
        hash_val = item.get('hash')
        md5 = item.get('md5')
        sha256 = item.get('sha256')
        sha512 = item.get('sha512')
        
        if hash_val:
            clean_hash = str(hash_val).strip()
            length = len(clean_hash)
            if length == 32:
                md5 = clean_hash
            elif length == 128:
                sha512 = clean_hash
            else:
                sha256 = clean_hash
                
        return {
            'is_tool': is_tool,
            'md5': md5,
            'sha256': sha256,
            'sha512': sha512
        }

    @staticmethod
    def _create_malware(incident_id, items, user_id):
        """Create malware/tool records from normalized JSON items with hash auto-detection."""
        count = 0
        for item in items:
            file_name = item.get('file_name')
            if not file_name:
                continue
            
            # Prepare fields
            fields = ImportService._clean_malware_fields(item)
            
            kwargs = {
                'incident_id': incident_id,
                'file_name': file_name,
                'md5': fields['md5'],
                'sha256': fields['sha256'],
                'sha512': fields['sha512'],
                'file_path': item.get('path'), # MAP path -> file_path
                'file_size': ImportService._parse_size(item.get('file_size')),
                'creation_time': ImportService._parse_date(item.get('creation_time')),
                'modification_time': ImportService._parse_date(item.get('modification_time')),
                'host': item.get('host'),
                'is_tool': fields['is_tool'],
                'description': item.get('description'),
                'created_by': user_id
            }
            
            valid_kwargs = ImportService._clean_kwargs(MalwareTool, **kwargs)
            malware = MalwareTool(**valid_kwargs)
            db.session.add(malware)
            count += 1
        return count

    @staticmethod
    def _create_host_iocs(incident_id, items, user_id):
        """Create host-based indicator records from normalized JSON items with artifact type normalization."""
        count = 0
        valid_types = HostBasedIndicator.ARTIFACT_TYPES
        
        for item in items:
            value = item.get('value') or item.get('artifact_value')
            if not value:
                continue
            
            # Normalize artifact type
            raw_type = str(item.get('type') or item.get('artifact_type') or 'other').lower().strip()
            artifact_type = 'other'
            
            if raw_type in valid_types:
                artifact_type = raw_type
            else:
                # Fuzzy matching
                if 'wmi' in raw_type:
                    artifact_type = 'wmi_event'
                elif 'asep' in raw_type or 'autorun' in raw_type:
                    artifact_type = 'asep'
                elif 'registry' in raw_type or 'key' in raw_type:
                    artifact_type = 'registry'
                elif 'task' in raw_type or 'scheduled' in raw_type:
                    artifact_type = 'scheduled_task'
                elif 'service' in raw_type:
                    artifact_type = 'service'
                elif 'file' in raw_type:
                    artifact_type = 'file'
                elif 'process' in raw_type:
                    artifact_type = 'process'
                elif 'archive' in raw_type:
                    artifact_type = 'file'  # Map Archive -> file
                
            kwargs = {
                'incident_id': incident_id,
                'artifact_type': artifact_type,
                'artifact_value': value,
                'host': item.get('host') or item.get('hostname'),
                'datetime': ImportService._parse_date(item.get('datetime')),
                'notes': item.get('notes'),
                'created_by': user_id
            }
            
            valid_kwargs = ImportService._clean_kwargs(HostBasedIndicator, **kwargs)
            ioc = HostBasedIndicator(**valid_kwargs)
            db.session.add(ioc)
            count += 1
        return count
