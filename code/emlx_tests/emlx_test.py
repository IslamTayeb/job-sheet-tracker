import emlx
import glob
import json

for filepath in glob.iglob("/Users/islamtayeb/Library/Mail/**/*.emlx", recursive=True):
    messages = []
    m = emlx.read(filepath)
    messages.append({
        'filepath': filepath,
        'subject': m.subject,
        'from': m.from_,
        'to': m.to,
        'date': str(m.date),
        'body': m.body
    })

    # Write to JSON file
    with open('emails.json', 'w') as f:
        json.dump(messages, f, indent=4)
