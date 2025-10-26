import csv
import html
import json
import random
import time
from io import StringIO
from typing import Dict, Any, List, Generator
import json

from fastapi import APIRouter, File, UploadFile, Form, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response, StreamingResponse, RedirectResponse, HTMLResponse

from sflib import SpiderFoot
from spiderfoot import SpiderFootDb, SpiderFootHelpers
from domain.state import state, get_dbh
from .main_schema import *
from .main_crud import *
from configs import logger


templates = Jinja2Templates(directory="templates")

router = APIRouter(
    prefix='',
)

@router.get("/", response_class=HTMLResponse, summary="Redirect to scan list page")
async def index(request: Request):
    """
    Redirects to /scanlist
    """
    scanlist_url = request.url_for("scan_list")
    return RedirectResponse(url=scanlist_url)


@router.get("/scanlist", response_class=HTMLResponse, summary="Show scan list page")
async def scan_list(request: Request) -> HTMLResponse:
    """
    Renders the main scan list page HTML.
    """
    return templates.TemplateResponse(
        "pages/scanlist/dashboard.html",
        {
            "request": request,
            "pageid": 'SCANLIST',
        }
    )

@router.get("/scanviz")
async def scan_viz(
    id: str,
    gexf: str = "0",
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Export entities from scan results for visualising.

    Args:
        id (str): scan ID (path parameter)
        gexf (str): '0' for JSON/browser visualization data,
                    any other value for GEXF file download.
        dbh (SpiderFootDb): Dependency injected database handler.

    Returns:
        Response: Either JSON data for visualization or a downloadable GEXF file.
    """
    if not id:
        return jsonify_error(404, "Scan ID required")

    data = dbh.scanResultEvent(id, filterFp=True)
    scan = dbh.scanInstanceGet(id)

    if not scan:
        return jsonify_error(404, f"Scan with ID '{id}' not found")

    scan_name = scan[0]
    root = scan[1]

    # --- Case 1: Return JSON for Visualization (gexf == "0") ---
    if gexf == "0":
        return json.loads(SpiderFootHelpers.buildGraphJson([root], data))

    # --- Case 2: Return GEXF file for download (gexf != "0") ---
    
    # 1. Generate GEXF content
    gexf_content = SpiderFootHelpers.buildGraphGexf([root], "SpiderFoot Export", data)

    # 2. Determine file name
    if not scan_name:
        fname = "SpiderFoot.gexf"
    else:
        # Note: Added a space or underscore to ensure separation, assuming it was missing in the original logic
        fname = f"{scan_name}_SpiderFoot.gexf" 
        
    # 3. Build Response with Headers
    headers = {
        'Content-Disposition': f"attachment; filename={fname}",
        'Content-Type': "application/gexf+xml", # Using a more specific MIME type for GEXF
        'Pragma': "no-cache"
    }
    
    # Use the base Response class for text content with custom headers and media type
    return Response(
        content=gexf_content,
        media_type="application/gexf+xml",
        headers=headers
    )

@router.get(
    "/newscan", 
    response_class=HTMLResponse, 
    summary="Configure a new scan page"
)
async def new_scan_page(
    request: Request, 
    dbh: SpiderFootDb = Depends(get_dbh)
) -> HTMLResponse:
    """
    Renders the HTML page for configuring a new SpiderFoot scan.
    """
    try:
        types = dbh.eventTypes()
    except Exception as e:
        logger.error(f"Error fetching event types: {e}", exc_info=True)
        return jsonify_error(500, "Failed to load scan data.")

    return templates.TemplateResponse(
        "pages/newscan/dashboard.html", 
        {
            "request": request,
            "pageid": 'NEWSCAN',
            "types": types,
            "modules": state.config.get('__modules__', {}),
            "scanname": "",
            "selectedmods": "",
            "scantarget": "",
        }
    )

@router.get(
    "/scaninfo", 
    response_class=HTMLResponse, 
    summary="Show information about a selected scan"
)
async def scan_info(
    id: str,
    request: Request,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> HTMLResponse:
    """
    Renders the scan information page for a specific scan ID.
    """
    res = dbh.scanInstanceGet(id)
    
    if res is None:
        return jsonify_error(404, "Scan ID not found.")

    # res[0] (scan name)은 HTML 템플릿에 안전하게 전달하기 위해 HTML escape 처리
    scan_name_escaped = html.escape(res[0])
    
    # 템플릿 렌더링
    return templates.TemplateResponse(
        "pages/scaninfo/dashboard.html",
        {
            "request": request,
            "id": id,
            "name": scan_name_escaped,
            "status": res[5],
            "pageid": "SCANLIST"
        }
    )

@router.get(
    "/opts",
    summary="모듈 및 전역 설정 페이지 표시",
    response_class=templates.TemplateResponse, # 응답 타입을 명시적으로 HTML 템플릿으로 설정
)
async def opts(
    request: Request,
    updated: str = None, 
) -> HTMLResponse:
    """
    전역 및 모듈 설정 페이지를 렌더링하고, 설정 업데이트 메시지를 표시합니다.

    Args:
        request: FastAPI 요청 객체
        updated: 설정이 성공적으로 업데이트되었음을 알리는 메시지
    
    Returns:
        HTML: 'opts.tmpl' 템플릿이 렌더링된 HTML 응답
    """

    token = random.SystemRandom().randint(0, 99999999)

    # 템플릿 렌더링
    return templates.TemplateResponse(
        "pages/opts/dashboard.html",
        {
            "request": request,
            "opts": state.config,
            "pageid": 'SETTINGS',
            "token": token,
            "updated": updated,
        }
    )

@router.get(
    "/scaneventresultexport"
)
async def scaneventresultexport(
    id: str,
    type: str,
    filetype: str = "csv",
    dialect: str = "excel",
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Get scan event result data in CSV or Excel format.
    """
    data = dbh.scanResultEvent(id, type)
    headers = ["Updated", "Type", "Module", "Source", "F/P", "Data"]
    filetype_lower = filetype.lower()
    fname_base = "SpiderFoot"

    if filetype_lower in ["xlsx", "excel"]:
        # --- Excel Export ---
        rows = list(process_data(data))
        fname = f"{fname_base}.xlsx"
        
        # Build the Excel file (assumes self.buildExcel is available via excel_builder)
        try:
            excel_bytes = buildExcel(rows, headers, sheetNameIndex=1)
        except Exception as e:
            logger.error(f'build excel: {e}', exc_info=True)
            return jsonify_error(500, f"Failed to generate Excel file: {e}")

        # Return the binary data using Response
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                'Content-Disposition': f'attachment; filename="{fname}"',
                'Pragma': 'no-cache',
            }
        )

    elif filetype_lower == 'csv':
        # --- CSV Export ---
        fname = f"{fname_base}.csv"

        def generate_csv() -> Generator[str, None, None]:
            """Generator to stream the CSV content."""
            # Use StringIO to capture CSV writer output
            fileobj = StringIO()
            # Note: The original used the 'dialect' parameter
            parser = csv.writer(fileobj, dialect=dialect)

            # Write headers
            parser.writerow(headers)
            yield fileobj.getvalue() # Yield headers

            # Write data rows
            for row in process_data(data):
                fileobj.seek(0)
                fileobj.truncate(0)
                parser.writerow(row)
                yield fileobj.getvalue() # Yield row data

        # Return the CSV content using StreamingResponse
        return StreamingResponse(
            content=generate_csv(),
            media_type="application/csv",
            headers={
                'Content-Disposition': f'attachment; filename="{fname}"',
                'Pragma': 'no-cache',
            }
        )

    else:
        return jsonify_error(400, f"Invalid export filetype: {filetype}. Must be 'csv' or 'xlsx'/'excel'.")

@router.get(
    "/scaneventresultexportmulti"
)
async def scaneventresultexportmulti(
    ids: str,
    filetype: str = "csv",
    dialect: str = "excel",
    dbh: SpiderFootDb = Depends(get_dbh),
):
    """
    Get scan event result data in CSV or Excel format for multiple scans.
    """
    scaninfo = {}
    data = []
    scan_name = ""
    id_list = [i.strip() for i in ids.split(',') if i.strip()]

    # 1. Fetch data for all valid IDs
    for id_str in id_list:
        meta = dbh.scanInstanceGet(id_str)
        scaninfo[id_str] = meta
        if meta is None:
            continue
        
        # meta[0] is the scan name
        scan_name = meta[0] 
        data.extend(dbh.scanResultEvent(id_str))

    # 2. Check if any data was retrieved
    if not data:
        return jsonify_error(400, "No data found for the specified scan IDs or no valid IDs provided.")

    # 3. Determine Filename
    filetype_lower = filetype.lower()
    if len(id_list) > 1 or scan_name == "":
        fname_base = "SpiderFoot"
    else:
        fname_base = scan_name + "-SpiderFoot"

    # 4. Define common headers
    headers = ["Scan Name", "Updated", "Type", "Module", "Source", "F/P", "Data"]

    # --- Excel Export ---
    if filetype_lower in ["xlsx", "excel"]:
        rows = list(process_multi_data(data, scaninfo))
        fname = f"{fname_base}.xlsx"
        
        # Call the placeholder Excel builder
        excel_bytes = buildExcel(rows, headers, sheetNameIndex=2)

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                'Content-Disposition': f'attachment; filename="{fname}"',
                'Pragma': 'no-cache',
            }
        )

    # --- CSV Export ---
    elif filetype_lower == 'csv':
        fname = f"{fname_base}.csv"

        def generate_csv() -> Generator[str, None, None]:
            """Generator to stream the CSV content."""
            fileobj = StringIO()
            
            try:
                parser = csv.writer(fileobj, dialect=dialect, escapechar='\\', quoting=csv.QUOTE_MINIMAL)
            except csv.Error as e:
                return jsonify_error(400, f"Invalid CSV dialect: {e}")

            # Write headers
            parser.writerow(headers)
            yield fileobj.getvalue()

            # Write data rows
            for row in process_multi_data(data, scaninfo):
                fileobj.seek(0)
                fileobj.truncate(0)
                parser.writerow(row)
                yield fileobj.getvalue()

        # Return streaming content with appropriate headers
        return StreamingResponse(
            content=(s.encode('utf-8') for s in generate_csv()), # Encode to bytes for StreamingResponse
            media_type="application/csv",
            headers={
                'Content-Disposition': f'attachment; filename="{fname}"',
                'Pragma': 'no-cache',
            }
        )

    else:
        return jsonify_error(400, f"Invalid export filetype: {filetype}. Must be 'csv', 'xlsx', or 'excel'.")
        
@router.get(
    "/optsexport"
)
def optsexport(
    pattern: str = None,
):
    """
    Export configuration settings in plain text (key=value) format.

    Args:
        pattern: pattern to filter configuration keys.

    Returns:
        Response: Configuration settings as a text/plain file attachment.
    """
    # Initialize SpiderFoot and serialize config (using the injected 'sf' instance)
    sf = SpiderFoot(state.config)
    conf = sf.configSerialize(state.config)
    content = ""

    # Build the configuration file content
    for opt in sorted(conf):
        # Skip internal/temporary options (those containing ":_" or starting with "_")
        if ":_" in opt or opt.startswith("_"):
            continue

        value = str(conf[opt])

        if pattern:
            # Only include options that match the pattern
            if pattern in opt:
                content += f"{opt}={value}\n"
        else:
            # Include all options
            content += f"{opt}={value}\n"

    # Set up the response headers for file download
    file_name = "SpiderFoot.cfg"
    
    # Return the content using FastAPI's Response class
    return Response(
        content=content,
        media_type="text/plain",
        headers={
            'Content-Disposition': f'attachment; filename="{file_name}"',
        }
    )

@router.get(
    "/scanexportlogs", 
    response_class=StreamingResponse,
    summary="Scan Log Export (CSV)"
)
async def scan_export_logs(
    id: str, 
    dialect: str = "excel",
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Get scan log in CSV format.
    """
    try:
        data = dbh.scanLogs(id, None, None, True)
    except Exception as e:
        logger.error(f'scan_export_logs: {e}', exc_info=True)
        return jsonify_error(400, "Scan ID not found or error accessing logs.")

    if not data:
        return jsonify_error(404, "Scan ID not found or logs are empty.")
    
    fileobj = StringIO()
    parser = csv.writer(fileobj, dialect=dialect)
    parser.writerow(["Date", "Component", "Type", "Event", "Event ID"])
    for row in data:
        parser.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[0] / 1000)),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            row[4]
        ])

    # StringIO의 내용을 bytes로 인코딩하고 Response를 반환합니다.
    csv_content = fileobj.getvalue().encode('utf-8')

    response_headers = {
        'Content-Disposition': f"attachment; filename=SpiderFoot-{id}.log.csv",
        'Content-Type': "text/csv", # "application/csv" 대신 "text/csv" 또는 "application/octet-stream" 사용
        'Pragma': "no-cache"
    }
    
    # Response를 사용하여 bytes 내용을 반환합니다.
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers=response_headers
    )

@router.get("/scancorrelationsexport",
            summary="Scan Correlation Export (CSV/Excel)"
)
async def scan_correlations_export(
    id: str,
    filetype: str = "csv",
    dialect: str = "excel",
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Get scan correlation data in CSV or Excel format.
    """
    try:
        scaninfo = dbh.scanInstanceGet(id)
        scan_name = scaninfo[0] if scaninfo else "UnknownScan"
    except Exception:
        return jsonify_error(404, "Could not retrieve info for scan.")

    try:
        correlations = dbh.scanCorrelationList(id)
    except Exception:
        return jsonify_error(500, "Could not retrieve correlations for scan.")

    headings = ["Rule Name", "Correlation", "Risk", "Description"]

    if filetype.lower() in ["xlsx", "excel"]:
        rows = []
        for row in correlations:
            correlation = row[1]
            rule_name = row[2]
            rule_risk = row[3]
            rule_description = row[5]
            rows.append([rule_name, correlation, rule_risk, rule_description])

        fname = f"{scan_name}-SpiderFoot-correlations.xlsx" if scan_name else "SpiderFoot-correlations.xlsx"
        
        excel_content = buildExcel(rows, headings, sheetNameIndex=0) # buildExcel 함수는 위에 정의된 것을 사용

        return Response(
            content=excel_content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                'Content-Disposition': f"attachment; filename={fname}",
                'Pragma': "no-cache"
            }
        )

    if filetype.lower() == 'csv':
        fileobj = StringIO()
        parser = csv.writer(fileobj, dialect=dialect)
        parser.writerow(headings)

        for row in correlations:
            correlation = row[1]
            rule_name = row[2]
            rule_risk = row[3]
            rule_description = row[5]
            parser.writerow([rule_name, correlation, rule_risk, rule_description])

        fname = f"{scan_name}-SpiderFoot-correlations.csv" if scan_name else "SpiderFoot-correlations.csv"
        csv_content = fileobj.getvalue().encode('utf-8')
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                'Content-Disposition': f"attachment; filename={fname}",
                'Pragma': "no-cache"
            }
        )

    return jsonify_error(400, "Invalid export filetype.")

@router.get(
    "/clonescan", 
    response_class=HTMLResponse, 
    summary="Clone an existing scan into a new scan form"
)
async def clone_scan(
    id: str,
    request: Request,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> HTMLResponse:
    """
    Clones an existing scan's configuration and pre-populates the new scan form.
    """
    info = dbh.scanInstanceGet(id)

    if not info:
        return jsonify_error(404, "Invalid scan ID.")
    
    try:
        types = dbh.eventTypes()
        scanconfig = dbh.scanConfigGet(id)
    except Exception as e:
        logger.error(f"Error accessing DB for clone scan {id}: {e}", exc_info=True)
        return jsonify_error(404, "Error loading scan configuration.")
    
    scanname = info[0]
    scantarget = info[1]

    if scanname == "" or scantarget == "" or len(scanconfig) == 0:
        return jsonify_error(404, "Something went wrong internally: Missing scan data.")

    # CherryPy의 로직을 따름: 타겟 타입이 인식되지 않으면 따옴표로 감쌈 (HTML 엔티티 사용)
    targetType = SpiderFootHelpers.targetTypeFromString(scantarget)
    if targetType is None:
        scantarget = "&quot;" + scantarget + "&quot;"
    
    # 모듈 리스트
    modlist = scanconfig.get('_modulesenabled', '').split(',')

    # 템플릿 렌더링
    return templates.TemplateResponse(
        "pages/newscan/dashboard.html",
        {
            "request": request,
            "pageid": 'NEWSCAN',
            "types": types,
            "modules": state.config.get('__modules__', {}),
            "selectedmods": modlist,
            "scanname": str(scanname),
            "scantarget": str(scantarget),
        }
    )


