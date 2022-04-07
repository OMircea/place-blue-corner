import datetime
import json
import requests
import time

from itertools import combinations
from websocket import create_connection
from typing import Tuple
from PIL import Image


class Runner():
    def __init__(self):
        # Authorization token used to make requests
        self.token = self._get_token_from_file()

        # 2000 x 1000 board
        # Has 24 possible color values
        # NOTE: This represents the actual canvas of r/place
        self.canvas = []

        # Represents the desired photo
        # Only the pixels that we want to change are accounted for
        # i.e. white pixels are ignored in this case
        self.target = self._load_target_canvas()

        # NOTE: The following values are represented in seconds
        #
        # Timestamp value when user can place again
        self.can_place_tile_at = -1
        # Add a buffer in case the request is made exactly
        # when cooldown expires to make sure it won't fail
        self.time_buffer = 10

        self.CANVAS_BLUE_WEB = 13
        self.BLUE_COLOR_SENT = 12

        # NOTE: Deprecated. I've used this in the
        # bot's first form, before having an actual image
        # to compare the r/place canvas to
        self.CANVAS_SIZE = 1000

    def _get_token_from_file(self):
        with open('token.txt') as f:
            return f.read().strip()

    def _reset_canvas(self):
        self.canvas = []

    def _load_target_canvas(self):
        """Get all non-white pixels
        """
        image = Image.open('blue.png')
        image.load()

        # Replace alpha channel with white color
        im = Image.new('RGB', image.size, (255, 255, 255))
        im.paste(image, None)

        target = []
        for i in range(im.size[0]):
            for j in range(im.size[1]):
                if im.getpixel((i, j)) == ((255, 255, 255)):
                    continue
                target.append((i, j))

        return target

    def _get_current_timestamp(self) -> int:
        return int(datetime.datetime.now().timestamp())

    def find_tile_to_fill_strategy_1(self) -> Tuple[int, int]:
        """DEPRECATED -- see self.CANVAS_SIZE comment

        Starting from the bottom right corner, go diagonally and find the first
        pixel that is not colored in blue.
        """
        for i in reversed(range(self.CANVAS_SIZE)):
            list_items = [j for j in range(i, self.CANVAS_SIZE)]

            crt_value = list_items[0]
            # Skip any extra generated combinations
            column_list = [t for t in combinations(
                list_items, 2) if crt_value in t]
            row_list = [(elem[1], elem[0]) for elem in column_list]
            top_left = [(crt_value, crt_value)]

            possible_combos = top_left + column_list + row_list

            for x_coord, y_coord in possible_combos:
                # Skip tiles that are already blue colored
                if self.canvas[x_coord, y_coord] == self.CANVAS_BLUE_WEB:
                    continue

                print(f'Found tile: ({x_coord}, {y_coord})')
                return x_coord, y_coord

    def find_tile_to_fill_strategy_2(self) -> Tuple[int, int]:
        """DEPRECATED -- see self.CANVAS_SIZE comment

        Starting from a tile that is positioned more towards the middle of 
        the blue corner, find a tile that is not  colored in blue, going down 
        diagonally towards the right bottom corner.
        """
        OFFSET = 20
        for i in range(self.CANVAS_SIZE - OFFSET, self.CANVAS_SIZE):
            for j in range(self.CANVAS_SIZE - OFFSET, self.CANVAS_SIZE):
                if self.canvas[i, j] == self.CANVAS_BLUE_WEB:
                    continue

                print(f'Found tile: ({i}, {j})')
                return i, j

    def find_canvas_target_first_difference(self) -> Tuple[int, int]:
        """Compares the target image with the r/place canvas 
        and returns the first pixel that is different.
        """
        for e1, e2 in self.target:
            # Skip blue colored tiles
            if self.canvas[e1, e2] == self.CANVAS_BLUE_WEB:
                continue

            print(f'Found tile: ({e1}, {e2})')
            return e1, e2

    def color_tile(self, x_coord: int, y_coord: int):
        """Color the specified tile
        """
        place_url = 'https://gql-realtime-2.reddit.com/query'
        headers_data = {
            'Authorization': f'Bearer {self.token}',
            'Content-type': 'application/json'
        }

        body = {
            "operationName": "setPixel",
            "variables": {
                "input": {
                    "actionName": "r/replace:set_pixel",
                    "PixelMessageData": {
                        "coordinate": {
                            "x": x_coord,
                            "y": y_coord
                        },
                        "colorIndex": self.BLUE_COLOR_SENT,
                        "canvasIndex": 0
                    }
                }
            },
            "query": "mutation setPixel($input: ActInput!) {\n  act(input: $input) {\n    data {\n      ... on BasicMessage {\n        id\n        data {\n          ... on GetUserCooldownResponseMessageData {\n            nextAvailablePixelTimestamp\n            __typename\n          }\n          ... on SetPixelResponseMessageData {\n            timestamp\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
        }

        r = requests.post(url=place_url, headers=headers_data,
                          data=json.dumps(body))
        resp = r.json()

        try:
            # nextAvailablePixelTimestamp has the following format: 1.648890585e+12
            # Divide by 10^3 so that it's easier to compare with the current timestamp
            # before fetching the canvas again
            self.can_place_tile_at = int(
                resp['data']['act']['data'][0]['data']['nextAvailablePixelTimestamp']/1000
            )
        except:
            # This can happen if the program is ran while the user is already on cooldown
            self.can_place_tile_at = int(
                resp['errors'][0]['extensions']['nextAvailablePixelTs']/1000
            )
            return

        print(f'Colored tile: ({x_coord}, {y_coord})')

    def set_canvas(self):
        ws = create_connection('wss://gql-realtime-2.reddit.com/query')
        ws.send(json.dumps({
            "type": "connection_init",
            "payload": {'Authorization': f'Bearer {self.token}'}
        }))

        obtained_map = False
        while not obtained_map:
            ws.send(json.dumps({"id": "2", "type": "start", "payload": {"variables": {"input": {"channel": {"teamOwner": "AFD2022", "category": "CANVAS", "tag": "0"}}}, "extensions": {}, "operationName": "replace",
                    "query": "subscription replace($input: SubscribeInput!) {\n  subscribe(input: $input) {\n    id\n    ... on BasicMessage {\n      data {\n        __typename\n        ... on FullFrameMessageData {\n          __typename\n          name\n          timestamp\n        }\n        ... on DiffFrameMessageData {\n          __typename\n          name\n          currentTimestamp\n          previousTimestamp\n        }\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"}}))
            # print('Any message')
            try:
                received_message = json.loads(ws.recv())
            except:
                print('The provided token has expired, update it then run again')
                self._reset_canvas()
                return

            print(received_message)
            try:
                canvas_dict = received_message['payload']['data']['subscribe']['data']
                if canvas_dict['__typename'] == 'FullFrameMessageData':
                    canvas_url = canvas_dict['name']
                    print(canvas_url)
                    with requests.get(canvas_url, stream=True) as r:
                        im = Image.open(r.raw)
                        pix = im.load()
                        self.canvas = pix
                        print('Fetched the canvas...')
                    obtained_map = True
            except:
                # Skip any other message until we can get the canvas
                pass
        ws.close()

    def run(self):
        try:
            while True:
                # No reason to get board or try to color if we're on cooldown
                time_now = self._get_current_timestamp()
                if time_now < self.can_place_tile_at:
                    print(
                        f'Currently on cooldown -- need to wait {self.can_place_tile_at - time_now} seconds more'
                    )

                    time.sleep(self.can_place_tile_at -
                               time_now + self.time_buffer)
                    continue

                self.set_canvas()
                if not self.canvas:
                    return

                # ttf_x, ttf_y = self.find_tile_to_fill_strategy_2()
                ttf_x, ttf_y = self.find_canvas_target_first_difference()
                self.color_tile(x_coord=ttf_x, y_coord=ttf_y)
        except KeyboardInterrupt:
            pass


r = Runner()
r.run()
