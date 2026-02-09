"""IOC defanging utilities for safe sharing of indicators.

Converts active IOCs into inert text representations:
  evil.com   → evil[.]com
  http://     → hxxp://
  1.2.3.4    → 1[.]2[.]3[.]4
  user@e.com → user[@]e[.]com
"""
import re
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from app.api.v1 import api_bp


def defang_value(value: str, ioc_type: str = 'auto') -> str:
    """Defang a single IOC value.

    Args:
        value: The IOC string to defang.
        ioc_type: One of 'auto', 'ip', 'domain', 'url', 'email'.
                  'auto' will try to detect the type.
    """
    if not value:
        return value

    result = value

    if ioc_type == 'auto':
        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', value):
            ioc_type = 'ip'
        elif '@' in value:
            ioc_type = 'email'
        elif re.match(r'^https?://', value, re.IGNORECASE):
            ioc_type = 'url'
        else:
            ioc_type = 'domain'

    if ioc_type == 'ip':
        result = value.replace('.', '[.]')
    elif ioc_type == 'domain':
        result = value.replace('.', '[.]')
    elif ioc_type == 'url':
        result = result.replace('http://', 'hxxp://')
        result = result.replace('https://', 'hxxps://')
        result = result.replace('ftp://', 'fxp://')
        # Defang the domain portion
        parts = result.split('://', 1)
        if len(parts) == 2:
            scheme, rest = parts
            slash_idx = rest.find('/')
            if slash_idx != -1:
                domain_part = rest[:slash_idx]
                path_part = rest[slash_idx:]
                result = f'{scheme}://{domain_part.replace(".", "[.]")}{path_part}'
            else:
                result = f'{scheme}://{rest.replace(".", "[.]")}'
    elif ioc_type == 'email':
        result = value.replace('@', '[@]').replace('.', '[.]')

    return result


def refang_value(value: str) -> str:
    """Reverse defanging — convert back to active IOC."""
    result = value
    result = result.replace('[.]', '.')
    result = result.replace('[@]', '@')
    result = result.replace('hxxp://', 'http://')
    result = result.replace('hxxps://', 'https://')
    result = result.replace('fxp://', 'ftp://')
    return result


def defang_text_block(text: str) -> str:
    """Defang all IOCs found in a block of text."""
    # URLs
    text = re.sub(r'https?://', lambda m: m.group().replace('http', 'hxxp'), text)
    text = re.sub(r'ftp://', 'fxp://', text)
    # IP addresses  — be careful not to double-defang
    text = re.sub(
        r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b',
        r'\1[.]\2[.]\3[.]\4',
        text,
    )
    # Email addresses
    text = re.sub(
        r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        lambda m: f'{m.group(1)}[@]{m.group(2).replace(".", "[.]")}',
        text,
    )
    # Remaining dots in domain-like strings (after scheme was already handled)
    # We leave this manual to avoid over-defanging regular text
    return text


@api_bp.route('/tools/defang', methods=['POST'])
@jwt_required()
def defang_iocs():
    """Defang one or more IOCs for safe sharing.

    Body: { "values": ["evil.com", "1.2.3.4", ...], "type": "auto" }
    OR:   { "text": "Found C2 at http://evil.com on 1.2.3.4" }
    """
    data = request.get_json() or {}

    # Mode 1: individual values
    values = data.get('values')
    if values:
        ioc_type = data.get('type', 'auto')
        results = [
            {'original': v, 'defanged': defang_value(v, ioc_type)}
            for v in values
        ]
        return jsonify({'items': results, 'total': len(results)}), 200

    # Mode 2: free text
    text = data.get('text', '')
    if text:
        defanged = defang_text_block(text)
        return jsonify({'original': text, 'defanged': defanged}), 200

    return jsonify({'error': 'bad_request', 'message': 'Provide "values" list or "text" string'}), 400


@api_bp.route('/tools/refang', methods=['POST'])
@jwt_required()
def refang_iocs():
    """Reverse-defang IOCs back to active form.

    Body: { "values": ["evil[.]com"] } OR { "text": "..." }
    """
    data = request.get_json() or {}

    values = data.get('values')
    if values:
        results = [
            {'defanged': v, 'original': refang_value(v)}
            for v in values
        ]
        return jsonify({'items': results, 'total': len(results)}), 200

    text = data.get('text', '')
    if text:
        return jsonify({'defanged': text, 'original': refang_value(text)}), 200

    return jsonify({'error': 'bad_request', 'message': 'Provide "values" list or "text" string'}), 400
