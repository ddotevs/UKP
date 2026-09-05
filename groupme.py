"""
GroupMe API wrapper for UKP Kickball
"""
import requests
import json
import io
from datetime import datetime

BASE_URL = 'https://api.groupme.com/v3'
IMAGE_SERVICE_URL = 'https://image.groupme.com/pictures'


def get_group_members(token, group_id):
    """Fetch members of a GroupMe group"""
    resp = requests.get(f'{BASE_URL}/groups/{group_id}', params={'token': token})
    resp.raise_for_status()
    group = resp.json()['response']
    return [
        {
            'user_id': m['user_id'],
            'nickname': m['nickname'],
            'image_url': m.get('image_url'),
        }
        for m in group.get('members', [])
    ]


def post_message(token, group_id, text, mentions=None):
    """Post a message to a GroupMe group with optional @mentions.
    
    mentions: list of dicts with 'user_id', 'start' (char offset), 'length'
    """
    payload = {
        'message': {
            'source_guid': f'ukp-{datetime.now().strftime("%Y%m%d%H%M%S%f")}',
            'text': text,
        }
    }
    if mentions:
        payload['message']['attachments'] = [{
            'type': 'mentions',
            'user_ids': [m['user_id'] for m in mentions],
            'loci': [[m['start'], m['length']] for m in mentions],
        }]
    
    resp = requests.post(
        f'{BASE_URL}/groups/{group_id}/messages',
        params={'token': token},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def create_event(token, conversation_id, name, description=None, start_at=None):
    """Create a calendar event in a GroupMe group.
    
    start_at: ISO 8601 datetime string
    Returns the event response including the event_id.
    """
    payload = {
        'name': name,
    }
    if description:
        payload['description'] = description
    if start_at:
        payload['start_at'] = start_at
    
    resp = requests.post(
        f'{BASE_URL}/conversations/{conversation_id}/events/create',
        params={'token': token},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def get_event(token, conversation_id, event_id):
    """Get event details including who has responded."""
    resp = requests.get(
        f'{BASE_URL}/conversations/{conversation_id}/events/{event_id}',
        params={'token': token},
    )
    resp.raise_for_status()
    return resp.json()


def get_event_respondents(token, conversation_id, event_id):
    """Get the set of user_ids who have responded (going/not going) to an event."""
    try:
        data = get_event(token, conversation_id, event_id)
        event = data.get('response', {}).get('event', {})
        responded = set()
        for user in event.get('going', []):
            responded.add(str(user.get('user_id', user) if isinstance(user, dict) else user))
        for user in event.get('not_going', []):
            responded.add(str(user.get('user_id', user) if isinstance(user, dict) else user))
        return responded
    except Exception:
        return set()


def build_game_message(game_date, opponent, players_in, groupme_user_map):
    """Build a game announcement message with @mentions for players marked IN.
    
    groupme_user_map: dict of player_name -> groupme_user_id
    Returns (text, mentions) tuple.
    """
    date_str = datetime.strptime(game_date, '%Y-%m-%d').strftime('%A, %B %-d')
    
    lines = [f'Game Day: {date_str}']
    if opponent:
        lines.append(f'vs. {opponent}')
    lines.append('')
    lines.append('Who\'s playing:')
    
    text_so_far = '\n'.join(lines) + '\n'
    mentions = []
    
    for player in sorted(players_in):
        gm_id = groupme_user_map.get(player)
        tag = f'@{player}'
        if gm_id:
            mentions.append({
                'user_id': gm_id,
                'start': len(text_so_far),
                'length': len(tag),
            })
        text_so_far += tag + '\n'
    
    return text_so_far.rstrip(), mentions


def build_reminder_message(non_responders, groupme_user_map):
    """Build a reminder message tagging players who haven't responded to the event.
    
    non_responders: list of player names who haven't responded
    groupme_user_map: dict of player_name -> groupme_user_id
    Returns (text, mentions) tuple.
    """
    text_so_far = 'Reminder: Please respond to the game event!\n\n'
    mentions = []
    
    for player in sorted(non_responders):
        gm_id = groupme_user_map.get(player)
        tag = f'@{player}'
        if gm_id:
            mentions.append({
                'user_id': gm_id,
                'start': len(text_so_far),
                'length': len(tag),
            })
        text_so_far += tag + '\n'
    
    return text_so_far.rstrip(), mentions


def upload_image(token, image_bytes):
    """Upload an image to GroupMe's image service. Returns the image URL."""
    resp = requests.post(
        IMAGE_SERVICE_URL,
        headers={
            'X-Access-Token': token,
            'Content-Type': 'image/png',
        },
        data=image_bytes,
    )
    resp.raise_for_status()
    return resp.json()['payload']['url']


def post_image_message(token, group_id, text, image_url):
    """Post a message with an attached image to a GroupMe group.
    Returns the full response including the message_id.
    """
    payload = {
        'message': {
            'source_guid': f'ukp-img-{datetime.now().strftime("%Y%m%d%H%M%S%f")}',
            'text': text,
            'attachments': [{
                'type': 'image',
                'url': image_url,
            }],
        }
    }
    resp = requests.post(
        f'{BASE_URL}/groups/{group_id}/messages',
        params={'token': token},
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def delete_message(token, conversation_id, message_id):
    """Delete a message from a GroupMe conversation."""
    resp = requests.delete(
        f'{BASE_URL}/conversations/{conversation_id}/messages/{message_id}',
        params={'token': token},
    )
    resp.raise_for_status()
    return resp.status_code


def pin_message(token, conversation_id, message_id):
    """Pin a message in a GroupMe conversation."""
    resp = requests.post(
        f'{BASE_URL}/conversations/{conversation_id}/messages/{message_id}/pin',
        params={'token': token},
    )
    resp.raise_for_status()
    return resp.json()
