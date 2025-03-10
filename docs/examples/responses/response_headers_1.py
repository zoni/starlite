from starlite import Controller, MediaType, Router, Starlite, get
from starlite.datastructures import ResponseHeader


class MyController(Controller):
    path = "/controller-path"
    response_headers = [
        ResponseHeader(name="controller-level-header", value="controller header", description="controller level header")
    ]

    @get(
        path="/handler-path",
        response_headers=[
            ResponseHeader(name="my-local-header", value="local header", description="local level header")
        ],
        media_type=MediaType.TEXT,
    )
    def my_route_handler(self) -> str:
        return "hello world"


router = Router(
    path="/router-path",
    route_handlers=[MyController],
    response_headers=[
        ResponseHeader(name="router-level-header", value="router header", description="router level header")
    ],
)

app = Starlite(
    route_handlers=[router],
    response_headers=[ResponseHeader(name="app-level-header", value="app header", description="app level header")],
)
