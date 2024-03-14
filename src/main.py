import asyncio

from converter import run_tls_message_converter
from runner import run_message_generator
from syncer import get_all_things

things = get_all_things()
print(f'{len(things)} Things in FROST server.')
things_for_message_generator = [t for t in things if t['name'] != 'SG1' and t['name'] != 'SG2']
things_for_tls_message_converter = [t for t in things if t['name'] == 'SG1' or t['name'] == 'SG2']

# Wait forever
async def main():
    await asyncio.gather(
        run_tls_message_converter(things_for_tls_message_converter),
        run_message_generator(things_for_message_generator),
    )

asyncio.run(main())
