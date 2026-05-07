import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

# Your Account SID and Auth Token from twilio.com/console
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
client = Client(account_sid, auth_token)

# Get the most recent message with media
messages = client.messages.list(limit=5)
for message in messages:
    print(f"Message SID: {message.sid}")
    print(f"Body: {message.body}")
    print(f"Num Media: {message.num_media}")
    
    if int(message.num_media) > 0:
        # If this message has media, let's try to access it
        media_list = client.messages(message.sid).media.list()
        for media in media_list:
            print(f"  Media SID: {media.sid}")
            print(f"  Content Type: {media.content_type}")
            print(f"  URI: {media.uri}")
            
            # Try to get the content URL
            content_url = media.uri.replace('.json', '/content')
            if not content_url.startswith('http'):
                content_url = f"https://api.twilio.com{content_url}"
            print(f"  Content URL: {content_url}")
        
        print("Found a message with media, testing complete!")
        break
else:
    print("No messages with media found")