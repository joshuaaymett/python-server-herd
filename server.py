import asyncio
import argparse
import time
import aiohttp
import json
from aiohttp import web
import re

PLACES_KEY = "AIzaSyDnj0vlZmTSnF3bSmmfO78b-D2ZS6LhnyY"


def get_server_port(name):
        server_port = 10789
        if (name == "Clark"):
            server_port = 10784
        elif (name == "Jaquez"):
            server_port = 10785
        elif (name == "Juzang"):
            server_port = 10786
        elif (name =="Bernard"):
            server_port = 10787
        elif (name == "Campbell"):
            server_port = 10788

        return server_port


def parse_location(location):
    loc_arr = re.findall(r"([+-][0-9.]+)", location)
    return loc_arr[0] + "%2c" + loc_arr[1]

async def get_place(location, radius, max_results):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={}&radius={}&key={}".format(location, radius, PLACES_KEY)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            r = await response.text()

            # Clean up formatting
            r_limited = json.loads(r)
            if ("results" in r_limited):
                if (len(r_limited['results']) > max_results):
                    r_limited['results'] = r_limited['results'][:max_results]
                    r_str_formatted = json.dumps(r_limited, indent=3, separators=(",", " : ")).replace("\n\n", "\n").rstrip("\n").replace("<", "\\u003c").replace(">", "\\u003e")

                    # Remove newlines from types arrays
                    types_arrs = re.findall(r"types\" : \[((.|\n)*?)\]", r_str_formatted)
                    for arr_str in types_arrs:
                        r_str_formatted = r_str_formatted.replace(arr_str[0], arr_str[0].replace(" ", "").replace("\n", " "))
                    return r_str_formatted
            return r

talks_to = {
    "Clark": ["Jaquez", "Juzang"],
    "Bernard": ["Jaquez", "Juzang", "Campbell"],
    "Juzang": ["Clark", "Bernard", "Campbell"],
    "Campbell": ["Bernard", "Juzang"],
    "Jaquez": ["Clark", "Bernard"]
}

class Server:
    def __init__(self, name, ip='127.0.0.1', port=10789, message_max_length=1e6):
        self.name = name
        self.ip = ip
        self.port = port
        self.message_max_length = int(message_max_length)
        self.f = open("{}-{}".format(name, time.time()), "w")
        
    clients = {

    }    

    def generate_client_data(self, og, time_diff, client_id, loc, t): 
        return "AT {} {} {} {} {}".format(og, time_diff, client_id, loc, t)

    def store_client_data(self, og, time_diff, client_id, loc, t):
        # Store response for future query
        self.clients[client_id] = self.generate_client_data(og, time_diff, client_id, loc, t)

    async def update_servers(self, msg):
        send_to = talks_to[self.name]

        for server_name in send_to:
            try: 
                _, writer = await asyncio.open_connection('127.0.0.1', get_server_port(server_name))
                self.f.write("\nConnected to " + server_name)
                writer.write(msg.encode())
                await writer.drain()
                writer.close()
                self.f.write("\nDisconnected from " + server_name)
            except:
                self.f.write("\nFailed to connect to " + server_name)

    async def handle_echo(self, reader, writer):
        data = await reader.read(self.message_max_length)
        message_dirty = data.decode()
        self.f.write(f"\nMessage Received: {message_dirty}")
        message = message_dirty.strip().split(" ")
        try:
            sendback_message = None

            # Split message into components
            cmd = message[0]

            if (cmd == "IAMAT"):
                client_id = message[1]
                lat_long = message[2]
                time_stamp = message[3]

                # Calculate difference in time between client and server
                time_diff =  "%+2.7f" % (time.time() - float(time_stamp))
                
                # Update self 
                self.store_client_data(og=self.name, time_diff=time_diff, client_id=client_id, loc=lat_long, t=time_stamp)

                # Update other servers
                update_message = "UPDATE {}".format(self.clients[client_id])
                await self.update_servers(update_message)
                
                # Response message
                sendback_message = f"AT {self.name} {time_diff} {client_id} {lat_long} {time_stamp}"
                
                writer.write(sendback_message.encode())
                self.f.write("\nResponse: " + sendback_message)
                await writer.drain()
            elif (cmd == "WHATSAT"):
                if (float(message[2]) > 50 or float(message[2]) < 0 or float(message[3]) > 20 or float(message[3]) < 0):
                    raise Exception("Radius must be a positive number no greater than 50. Results must be a positive number no greater than 20.")
                
                if (message[1] in self.clients):
                    parsed_loc = parse_location(self.clients[message[1]].split(" ")[4])
                    places_response = await get_place(parsed_loc, float(message[2])*1000, int(message[3]))
                    sendback_message = self.clients[message[1]] + "\n" + str(places_response) + "\n\n"
                    writer.write(sendback_message.encode())
                    self.f.write("\nResponse: " + sendback_message)
                    await writer.drain()
                else:
                    sendback_message = "{}\n\n"
                    writer.write(sendback_message.encode())
                    self.f.write("\nResponse: " + sendback_message)
                    await writer.drain()


            # Updates other servers with information. e.g. UPDATE client_id lat_long time_stamp
            elif (cmd == "UPDATE"):
                if (message[4] not in self.clients or self.clients[message[4]] != self.generate_client_data(og=message[2], time_diff=message[3], client_id=message[4], loc=message[5], t=message[6])):  
                    self.store_client_data(og=message[2], time_diff=message[3], client_id=message[4], loc=message[5], t=message[6])

                    # Update other servers
                    update_message = "UPDATE {}".format(self.clients[message[4]])
                    await self.update_servers(update_message)
            else:
                sendback_message = "? {}".format(message_dirty)
                writer.write(sendback_message.encode())
                self.f.write("\nResponse: " + sendback_message)
                await writer.drain()
            
        except Exception as e:
            # Handle error response
            sendback_message = "? {}".format(message_dirty)
            writer.write(sendback_message.encode())
            self.f.write("\nResponse: " + sendback_message)
            await writer.drain()
        writer.close()

    async def run_forever(self):
        server = await asyncio.start_server(self.handle_echo, self.ip, self.port)

        # Serve requests until Ctrl+C is pressed
        print(f'serving on {server.sockets[0].getsockname()}')

        async with server:
            await server.serve_forever()
        # Close the server
        server.close()

    def close_file(self):
        self.f.close()

def main():
    # Get server name
    parser = argparse.ArgumentParser('Server argparse')
    parser.add_argument('server_name', type=str,
                        help='Server name input')
    args = parser.parse_args()
    name = args.server_name

    # Run server
    server = Server(name, port=get_server_port(name))
    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        server.close_file()
        pass


if __name__ == '__main__':
    main()