import html

from fastapi.responses import JSONResponse


def searchBase(dbh, id: str = None, eventType: str = None, value: str = None) -> list:
    """Search.

    Args:
        id (str): scan ID
        eventType (str): TBD
        value (str): TBD

    Returns:
        list: search results
    """
    retdata = []

    if not id and not eventType and not value:
        return retdata

    if not value:
        value = ''

    regex = ""
    if value.startswith("/") and value.endswith("/"):
        regex = value[1:len(value) - 1]
        value = ""

    value = value.replace('*', '%')
    if value in [None, ""] and regex in [None, ""]:
        value = "%"
        regex = ""

    criteria = {
        'scan_id': id or '',
        'type': eventType or '',
        'value': value or '',
        'regex': regex or '',
    }

    try:
        data = dbh.search(criteria)
    except Exception:
        return retdata

    for row in data:
        lastseen = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[0]))
        escapeddata = html.escape(row[1])
        escapedsrc = html.escape(row[2])
        retdata.append([lastseen, escapeddata, escapedsrc,
                        row[3], row[5], row[6], row[7], row[8], row[10],
                        row[11], row[4], row[13], row[14]])

    return retdata

def clean_user_input(inputList: list) -> list:
    """Convert data to HTML entities; except quotes and ampersands.

    Args:
        inputList (list): list of strings to sanitize

    Returns:
        list: sanitized input

    Raises:
        TypeError: inputList type was invalid

    Todo:
        Review all uses of this function, then remove it.
        Use of this function is overloaded.
    """
    if not isinstance(inputList, list):
        raise TypeError(f"inputList is {type(inputList)}; expected list()")

    ret = list()

    for item in inputList:
        if not item:
            ret.append('')
            continue
        c = html.escape(item, True)

        # Decode '&' and '"' HTML entities
        c = c.replace("&amp;", "&").replace("&quot;", "\"")
        ret.append(c)

    return ret

def jsonify_error(status: int, message: str) -> JSONResponse:
    """JSON 형식의 에러 응답을 반환합니다."""
    return JSONResponse(
        status_code=status,
        content={
            'error': {
                'http_status': status,
                'message': message,
            }
        }
    )