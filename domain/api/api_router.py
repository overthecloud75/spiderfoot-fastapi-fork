import time
from copy import deepcopy
import multiprocessing as mp
import json

from fastapi import APIRouter, File, UploadFile, Form, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from sflib import SpiderFoot
from sfscan import startSpiderFootScanner
from spiderfoot import SpiderFootDb, SpiderFootHelpers
from domain.state import state, get_dbh
from .api_schema import *
from .api_crud import *
from configs import logger


router = APIRouter(
    prefix='/api',
)

@router.post(
    "/scanlist",
    response_model=ScanListResponse,
    summary="스캔 목록을 JSON 형식으로 반환",
)
async def post_scan_list(
    dbh: SpiderFootDb = Depends(get_dbh)
): 
    """
    데이터베이스에서 모든 스캔의 목록과 요약 정보를 조회합니다.
    """
    data = dbh.scanInstanceList()
    retdata = []

    for row in data:
        scan_id, name, target, created_ts, started_ts, finished_ts, status, progress = row

        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_ts))

        riskmatrix = {
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0
        }
        
        # 'scanCorrelationSummary' 호출
        correlations = dbh.scanCorrelationSummary(scan_id, by="risk")
        if correlations:
            for c in correlations:
                riskmatrix[c[0]] = c[1]

        if started_ts == 0:
            started = "Not yet"
        else:
            started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_ts))

        if finished_ts == 0:
            finished = "Not yet"
        else:
            finished = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished_ts))

        retdata.append({
            "id": scan_id,
            "name": name,
            "target": target,
            "created": created,
            "started": started,
            "finished": finished,
            "status": status,
            "progress": progress,
            "risk_matrix": riskmatrix
        })

    return retdata

@router.post(
    "/scansummary",
    summary="스캔 결과 요약 정보 반환",
)
async def scan_summary(
    payload: ScanSummaryRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    특정 스캔 ID에 대한 결과 요약 정보를 반환하며, 
    이벤트 유형별 개수, 최종 확인 시간, False Positive 개수 등을 포함합니다.
    """
    id = payload.id
    by = payload.by
    retdata = []

    try:
        # 1. 스캔 결과 요약 데이터 조회
        scandata = dbh.scanResultSummary(id, by)
    except Exception as e:
        logger.error(e, exc_info=True)
        # DB 연결 실패 또는 데이터 조회 실패 시 500 에러 대신 빈 리스트 반환 (원래 로직 유지)
        return retdata

    try:
        # 2. 스캔 인스턴스 (상태) 정보 조회
        statusdata = dbh.scanInstanceGet(id)
    except Exception as e:
        logger.error(e, exc_info=True)
        # DB 연결 실패 또는 데이터 조회 실패 시 빈 리스트 반환 (원래 로직 유지)
        return retdata

    # 3. 데이터 처리 및 포맷 변경
    for row in scandata:
        # row: (event_type, count, last_seen_ts, fp_count, unique_count)
        if row[0] == "ROOT":
            continue

        # 시간 형식 변환
        lastseen_ts = row[2]
        lastseen = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(lastseen_ts))
        
        retdata.append([row[0], row[1], lastseen, row[3], row[4], statusdata[5]])
    return retdata

@router.post(
    "/scanstatus",
    summary="스캔의 기본 상태 정보 반환",
    response_model=ScanStatus,
)
async def scanstatus(
    payload: ScanRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    특정 스캔 ID에 대한 이름, 대상, 시간 정보, 상태 및 위험도 요약을 반환합니다.
    """
    id = payload.id
    data = dbh.scanInstanceGet(id)

    if not data:
        # 스캔 ID가 유효하지 않으면 빈 리스트 반환
        return []

    # 타임스탬프를 시간 문자열로 변환
    created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data[2]))
    started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data[3]))
    ended = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data[4]))
    
    # 위험도 매트릭스 초기화 및 구성
    riskmatrix = {
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "INFO": 0
    }
    correlations = dbh.scanCorrelationSummary(id, by="risk")
    if correlations:
        for c in correlations:
            riskmatrix[c[0]] = c[1]

    return {
        "name": data[0],
        "target": data[1],
        "created": created,
        "started": started,
        "ended": ended,
        "status": data[5],
        "risk_matrix": riskmatrix
    }

@router.post(
    "/scanerrors", 
    response_model=ScanErrorResponse
)
async def scan_errors(
    payload: ScanErrorsRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Scan error data.

    Args:
        id (str): scan ID 
        limit (int): limit number of results 
        dbh (SpiderFootDb): Dependency injected database handler.
    """
    retdata = []

    id = payload.id
    limit = payload.limit

    try:
        data = dbh.scanErrors(id, limit)
    except Exception as e:
        logger.error(f'scan errors: {e}', exc_info=True)
        return retdata

    for row in data:
        # row[0] is timestamp in milliseconds
        generated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[0] / 1000))
        
        retdata.append(ScanError(
            generated=generated,
            module=row[1],
            error_message=html.escape(str(row[2]))
        ))

    return retdata

@router.post("/scancorrelations")
async def scan_correlations(
    payload: ScanRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Correlation results from a scan.

    Args:
        id (str): scan ID (path parameter)
        dbh (SpiderFootDb): Dependency injected database handler.

    """
    id = payload.id
    retdata = []

    try:
        corrdata = dbh.scanCorrelationList(id)
    except Exception as e:
        # Adhering to the original function's logic: return an empty list on exception
        logger.error(f'scan correlations: {e}', exc_info=True)
        return retdata

    for row in corrdata:
        retdata.append([row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]])
    return retdata

@router.post("/scanopts")
async def scanopts(
    payload: ScanRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Return configuration used for the specified scan as JSON.

    Args:
        id: scan ID

    Returns:
        dict: scan options for the specified scan
    """
    id = payload.id
    ret = {}

    # 1. Get scan metadata
    meta = dbh.scanInstanceGet(id)
    if not meta:
        return jsonify_error(404, f"Scan ID {id} not found.")

    # 2. Format start/finish times
    # meta is assumed to be a tuple/list: (id, name, target, started_timestamp, finished_timestamp, status)
    started_ts, finished_ts = meta[3], meta[4]

    if started_ts != 0:
        started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_ts))
    else:
        started = "Not yet"

    if finished_ts != 0:
        finished = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished_ts))
    else:
        finished = "Not yet"

    # 3. Build 'meta' and 'config' results
    ret['meta'] = [meta[0], meta[1], meta[2], started, finished, meta[5]]
    ret['config'] = dbh.scanConfigGet(id)
    ret['configdesc'] = {}

    # 4. Populate 'configdesc'
    globaloptdescs = state.config.get('__globaloptdescs__', {})
    modules = state.config.get('__modules__', {})

    for key, value in ret['config'].items():
        if ':' not in key:
            # Global option
            ret['configdesc'][key] = globaloptdescs.get(key, f"{key} (legacy)")
        else:
            # Module-specific option
            try:
                modName, modOpt = key.split(':', 1)
            except ValueError:
                continue

            module_info = modules.get(modName)
            if module_info:
                optdescs = module_info.get('optdescs', {})
                if modOpt in optdescs:
                    ret['configdesc'][key] = optdescs[modOpt]
    return ret

@router.post("/scanlog")
async def scanlog(
    payload: ScanLogRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Retrieve scan log data for a specified scan ID.

    Args:
        id: The ID of the scan.
        limit: Maximum number of log entries.
        rowId: Row ID for pagination.
        reverse: Direction of log retrieval.
    """
    id = payload.id
    limit = payload.limit
    rowId = payload.rowId
    reverse = payload.reverse
    retdata = []

    try:
        # Call the database method with all parameters
        data = dbh.scanLogs(id, limit, rowId, reverse)
    except Exception as e:
        logger.error('scan log: {e}', exc_info=True)
        return retdata

    for row in data:
        timestamp_s = row[0] / 1000
        generated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp_s))

        # html.escape is used to sanitize the log message before sending to the client
        escaped_message = html.escape(str(row[3]))
        retdata.append([generated, row[1], row[2], escaped_message, row[4]])

    return retdata

@router.post("/savesettings")
async def savesettings(
    allopts: str = Form(...),
    token: str = Form(...,),
    configFile: UploadFile = File(None, description="configuration file to upload."),
    dbh: SpiderFootDb = Depends(get_dbh), 
):
    """
    Save settings, also used to completely reset them to default.
    """
    # 1. Handle File Upload (If present and file is not empty)
    if configFile and configFile.filename and configFile.file:
        try:
            # Read and decode file contents
            contents = configFile.file.read()
            if not contents:
                raise ValueError("Uploaded file is empty.")

            contents = contents.decode('utf-8')

            # Parse the key=value configuration file format
            tmp = {}
            for line in contents.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"): # Skip empty lines and comments
                    continue

                # Split only on the first '=' to handle values containing '='
                parts = line.split("=", 1)
                opt_key = parts[0].strip()
                opt_value = parts[1].strip() if len(parts) > 1 else ""
                
                tmp[opt_key] = opt_value

            # Overwrite allopts with the JSON serialization of the file contents
            allopts = json.dumps(tmp)

        except Exception as e:
            logger.error(f'save settings: {e}', exc_info=True)
            # Match original error handling for file parsing failure
            return jsonify_error(400, f"Failed to parse input file. Was it generated from SpiderFoot? ({e})")
        finally:
            # Close the file stream after reading
            configFile.file.close()

    # 2. Handle Reset Command
    if allopts == "RESET":
        if reset_settings(dbh):
            # Success redirect
            return RedirectResponse(
                url=f"/opts?updated=1",
                status_code=303 # HTTP 303 See Other is generally preferred for POST success redirects
            )
        # Failure error
        return jsonify_error(500, "Failed to reset settings.")

    # 3. Save Settings
    try:
        # Load user options from JSON string
        useropts = json.loads(allopts)
        cleanopts = {}

        # Clean user input (using placeholder function)
        for opt, value in useropts.items():
            cleanopts[opt] = clean_user_input([value])[0]
        # Deepcopy the current configuration
        currentopts = deepcopy(state.config)
        sf = SpiderFoot(state.config)
        new_config = sf.configUnserialize(cleanopts, currentopts)
        
        # Save the finalized, serialized config to the database
        dbh.configSet(sf.configSerialize(new_config))
    except json.JSONDecodeError:
        return jsonify_error(400, "The 'allopts' data is not valid JSON.")
    except Exception as e:
        logger.error(e, exc_info=True)
        return jsonify_error(500, f"Processing one or more of your inputs failed: {e}")


    # 5. Success Redirect
    return RedirectResponse(
        url=f"/opts?updated=1",
        status_code=303
    )

@router.post("/startscan")
def startscan(
    request: Request,
    scanname: str = Form(None, description="Scan name."),
    scantarget: str = Form(None, description="Scan target."),
    modulelist: str = Form(None, description="Comma separated list of modules (prefixed with 'module_' in original)."),
    typelist: str = Form(None, description="Comma separated list of event types (prefixed with 'type_' in original)."),
    usecase: str = Form(None, description="Selected module group (passive, investigate, footprint, all)."),
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """Initiate a scan."""
    
    # 1. Clean and Validate Input
    scanname_cleaned, scantarget_cleaned = clean_user_input([scanname, scantarget])

    if not scanname_cleaned:
        return jsonify_error(400, "Scan name was not specified.") 
    if not scantarget_cleaned:
        return jsonify_error(400, "Scan target was not specified.") 
    if not typelist and not modulelist and not usecase:
        return jsonify_error(400, "No modules specified for scan.") 
    
    # 2. Validate Target Type
    targetType = SpiderFootHelpers.targetTypeFromString(scantarget_cleaned)
    if targetType is None:
        return jsonify_error(400, "Invalid target type. Could not recognize it as a target SpiderFoot supports.") 
    
    # 3. Setup and Module Selection Logic
    
    # Snapshot the current configuration for the new scan process
    cfg = deepcopy(state.config)
    sf = SpiderFoot(cfg)
    modlist = []

    # A. User selected modules explicitly
    if modulelist:
        # Original: modulelist.replace('module_', '').split(',')
        modlist = [m.strip() for m in modulelist.split(',') if m.strip()]

    # B. User selected types (and no explicit modules)
    elif typelist:
        typesx = [t.strip().replace('type_', '') for t in typelist.split(',') if t.strip()]

        # Logic to trace module dependencies (replicated from original)
        modlist = sf.modulesProducing(typesx)
        newmodcpy = deepcopy(modlist)

        while newmodcpy:
            newmods = []
            for etype in sf.eventsToModules(newmodcpy):
                xmods = sf.modulesProducing([etype])
                for mod in xmods:
                    if mod not in modlist:
                        modlist.append(mod)
                        newmods.append(mod)
            newmodcpy = deepcopy(newmods)

    # C. User selected a use case (and no modules/types)
    elif usecase:
        for mod, info in cfg['__modules__'].items():
            if usecase == 'all' or usecase in info.get('group', []):
                modlist.append(mod)

    # Final check for modules
    if not modlist:
        return jsonify_error(400, "No modules specified for scan.") 

    # 4. Final Module List Cleanup
    if "sfp__stor_db" not in modlist:
        modlist.append("sfp__stor_db")
    if "sfp__stor_stdout" in modlist:
        modlist.remove("sfp__stor_stdout")
    modlist.sort()

    # 5. Target Cleaning
    if targetType in ["HUMAN_NAME", "USERNAME", "BITCOIN_ADDRESS"]:
        scantarget_cleaned = scantarget_cleaned.replace("\"", "")
    else:
        scantarget_cleaned = scantarget_cleaned.lower()

    # 6. Start the Scan Process
    scanId = SpiderFootHelpers.genScanInstanceId()
    
    try:
        p = mp.Process(
            target=startSpiderFootScanner, 
            args=(state.loggingQueue, scanname_cleaned, scanId, scantarget_cleaned, targetType, modlist, cfg)
        )
        p.daemon = True
        p.start()
    except Exception as e:
        logger.error(f"[-] Scan [{scanId}] failed: {e}", exc_info=True)
        return jsonify_error(500, f"Scan [{scanId}] failed: {e}") 

    # 7. Wait for Initialization (Blocking operation)    
    timeout = 10
    start_time = time.time()
    while dbh.scanInstanceGet(scanId) is None and (time.time() - start_time) < timeout:
        logger.info("Waiting for the scan to initialize...")
        time.sleep(1)
        
    if dbh.scanInstanceGet(scanId) is None:
        return jsonify_error(500, "Scan failed to initialize within the timeout.") 

    # JSON response for API clients
    return JSONResponse(
        content={"scanId": scanId},
        status_code=200
    )

@router.post("/search")
async def search(
    dbh: SpiderFootDb = Depends(get_dbh),
    id: str = Form(...),
    eventType: str = Form(None),
    value: str = Form(None),
):
    """
    Search scans.

    Args:
        id (str): filter search results by scan ID
        eventType (str): filter search results by event type
        value (str): filter search results by event value

    Returns:
        list: search results
    """
    try:
        results = searchBase(dbh, id, eventType, value)
        return JSONResponse(content=results)
    except Exception as e:
        logger.error(f"[-] search [{id}] failed: {e}", exc_info=True)
        return JSONResponse(content=[], status_code=500)

@router.post("/scaneventresults")
async def scaneventresults(
    payload: ScanEventResutsRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Return all event results for a scan as JSON.
    """
    id = payload.id
    eventType = payload.eventType
    filterfp = payload.filterfp
    correlationId = payload.correlationId
    retdata = []

    if not eventType:
        eventType = 'ALL'

    try:
        data = dbh.scanResultEvent(id, eventType, filterfp, correlationId=correlationId)
    except Exception:
        return JSONResponse(content=retdata, status_code=500)

    for row in data:
        lastseen = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[0]))
        retdata.append([
            lastseen,
            html.escape(str(row[1])),
            html.escape(str(row[2])),
            row[3],
            row[5],
            row[6],
            row[7],
            row[8],
            row[13] if len(row) > 13 else None,
            row[14] if len(row) > 14 else None,
            row[4],
        ])

    return JSONResponse(content=retdata)

@router.post("/scaneventresultsunique")
async def scaneventresultsunique(
    payload: ScanEventResultsUniqueRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> JSONResponse:
    """
    Return unique event results for a scan as JSON.

    Args:
        id (str): filter search results by scan ID
        eventType (str): filter search results by event type
        filterfp (bool): remove false positives from search results

    Returns:
        JSONResponse: list of unique search results
    """
    id = payload.id
    eventType = payload.eventType
    filterfp = payload.filterfp
    retdata = []

    try:
        data = dbh.scanResultEventUnique(id, eventType, filterfp)
    except Exception:
        return JSONResponse(content=retdata)

    for row in data:
        escaped = html.escape(row[0])
        retdata.append([escaped, row[1], row[2]])

    return JSONResponse(content=retdata)

@router.post("/scanelementtypediscovery")
async def scanelementtypediscovery(
    payload: ScanElementTypeDiscoveryRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> JSONResponse:
    """
    Scan element type discovery.

    Args:
        id (str): scan ID
        eventType (str): filter by event type

    Returns:
        dict: { "tree": ..., "data": ... }
    """
    id = payload.id
    eventType = payload.eventType
    pc = {}
    datamap = {}
    retdata = {}

    try:
        leafSet = dbh.scanResultEvent(id, eventType)
        datamap, pc = dbh.scanElementSourcesAll(id, leafSet)
    except Exception:
        return JSONResponse(content=retdata)

    # ROOT 제거
    pc.pop('ROOT', None)
    retdata['tree'] = SpiderFootHelpers.dataParentChildToTree(pc)
    retdata['data'] = datamap

    return JSONResponse(content=retdata)

@router.post("/resultsetfp")
async def resultsetfp(
    payload: ResultSetFpRequest,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> JSONResponse:
    """
    Set a bunch of results (hashes) as false positive.

    Args:
        id (str): scan ID
        resultids (str): JSON string of result IDs (list)
        fp (str): 0 or 1

    Returns:
        JSONResponse: status and message
    """
    id = payload.id
    resultids = payload.resultids
    fp = payload.fp

    if fp not in ["0", "1"]:
        return JSONResponse(content=["ERROR", "No FP flag set or not set correctly."], status_code=400)

    try:
        ids = json.loads(resultids)
        if not isinstance(ids, list):
            raise ValueError("resultids must be a list")
    except Exception:
        return JSONResponse(content=["ERROR", "No IDs supplied or invalid format."], status_code=400)

    # 스캔 상태 확인
    status = dbh.scanInstanceGet(id)
    if not status:
        return JSONResponse(content=["ERROR", f"Invalid scan ID: {id}"], status_code=404)

    if status[5] not in ["ABORTED", "FINISHED", "ERROR-FAILED"]:
        return JSONResponse(content=[
            "WARNING",
            "Scan must be in a finished state when setting False Positives."
        ])

    # 부모 FP 확인
    if fp == "0":
        data = dbh.scanElementSourcesDirect(id, ids)
        for row in data:
            if str(row[14]) == "1":
                return JSONResponse(content=[
                    "WARNING",
                    f"Cannot unset element {id} as False Positive if a parent element is still False Positive."
                ])

    # 자식도 함께 FP 설정
    childs = dbh.scanElementChildrenAll(id, ids)
    allIds = ids + childs

    ret = dbh.scanResultsUpdateFP(id, allIds, fp)
    if ret:
        return JSONResponse(content=["SUCCESS", ""])

    return JSONResponse(content=["ERROR", "Exception encountered."], status_code=500)

@router.get("/scandelete")
async def scandelete(
    id: str,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Delete one or more scans.

    Args:
        id: comma separated list of scan IDs

    Returns:
        dict: Success confirmation
    """
    # 1. Input Validation (No scan specified)
    if not id.strip():
        logger.error('No scan specified', exc_info=True)
        return jsonify_error(404, "No scan specified.")

    ids = [i.strip() for i in id.split(',') if i.strip()]

    # 2. Pre-check: Existence and Status
    for scan_id in ids:
        res = dbh.scanInstanceGet(scan_id)

        if not res:
            # Replaces self.jsonify_error('404', f"Scan {scan_id} does not exist")
            logger.error(f"Scan {scan_id} does not exist.", exc_info=True)
            return jsonify_error(404, f"Scan {scan_id} does not exist.")

        scan_status = res[5]
        if scan_status in ["RUNNING", "STARTING", "STARTED"]:
            # Replaces self.jsonify_error('400', ...)
            return jsonify_error(400, f"Scan {scan_id} is {scan_status}. You cannot delete running scans.")

    # 3. Execution: Delete Scans
    for scan_id in ids:
        dbh.scanInstanceDelete(scan_id)

    # 4. Success Response
    # Returning a clear success message is better practice.
    return {"result": "success", "deleted_ids": ids}

@router.get("/stopscan")
def stopscan(
    id: str,
    dbh: SpiderFootDb = Depends(get_dbh)
) -> Dict[str, Any]:
    """
    Request abortion for one or more running scans.

    Args:
        id: comma separated list of scan IDs

    Returns:
        dict: Success confirmation
    """
    # 1. Input Validation (No scan specified)
    if not id.strip():
        return jsonify_error(404, "No scan specified.")

    ids = [i.strip() for i in id.split(',') if i.strip()]

    # 2. Pre-check: Existence and Status
    for scan_id in ids:
        res = dbh.scanInstanceGet(scan_id)

        if not res:
            return jsonify_error(404, f"Scan {scan_id} does not exist.")

        scan_status = res[5]

        if scan_status == "FINISHED":
            return jsonify_error(400, f"Scan {scan_id} has already finished.")

        if scan_status == "ABORTED":
            return jsonify_error(400, f"Scan {scan_id} has already aborted.")

        if scan_status not in ["RUNNING", "STARTING"]:
            return jsonify_error(400, f"The scan {scan_id} is in state '{scan_status}'. Only RUNNING or STARTING scans can be stopped.")

    # 3. Execution: Request Abortion
    for scan_id in ids:
        # Note: Setting status to ABORT-REQUESTED signals the background process to stop.
        dbh.scanInstanceSet(scan_id, status="ABORT-REQUESTED")

    # 4. Success Response
    # The original returned "" with json_out(), which is JSON `{}`.
    return {"result": "success", "requested_abort_ids": ids}

@router.get(
    "/rerunscan", 
    summary="Rerun a Scan"
)
async def rerun_scan(
    id: str,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Rerun a scan and redirect to the new scan's info page.
    """
    cfg = deepcopy(state.config)
    
    info = dbh.scanInstanceGet(id)
    if not info:
        return jsonify_error(404, "Invalid scan ID.")

    scanname = info[0]
    scantarget = info[1]

    scanconfig = dbh.scanConfigGet(id)
    if not scanconfig:
        return jsonify_error(500, f"Error loading config from scan: {id}")

    modlist = scanconfig.get('_modulesenabled', '').split(',')
    if "sfp__stor_stdout" in modlist:
        modlist.remove("sfp__stor_stdout")

    targetType = SpiderFootHelpers.targetTypeFromString(scantarget)
    if not targetType:
        targetType = SpiderFootHelpers.targetTypeFromString(f'"{scantarget}"')

    if targetType not in ["HUMAN_NAME", "BITCOIN_ADDRESS"]:
        scantarget = scantarget.lower()

    # Start running a new scan
    scanId = SpiderFootHelpers.genScanInstanceId()
    try:
        # startSpiderFootScanner는 동기 함수이므로, 멀티프로세스 로직은 그대로 유지
        p = mp.Process(target=startSpiderFootScanner, args=(state.loggingQueue, scanname, scanId, scantarget, targetType, modlist, cfg))
        p.daemon = True
        p.start()
    except Exception as e:
        logger.error(f"[-] Scan [{scanId}] failed: {e}", exc_info=True)
        return jsonify_error(500, f"Scan [{scanId}] failed to start: {e}")

    start_time = time.time()
    while dbh.scanInstanceGet(scanId) is None:
        if time.time() - start_time > 10: # 10초 타임아웃
            logger.error(f"[-] Scan [{scanId}] failed to initialize in time.", exc_info=True)
            return jsonify_error(500, f"Scan [{scanId}] failed to initialize in time.")
        logger.info("Waiting for the scan to initialize...")
        time.sleep(1)

    return RedirectResponse(url=f"/scaninfo?id={scanId}", status_code=302)

@router.get("/rerunscanmulti")
async def rerun_scan_multi(
    ids: str,
    dbh: SpiderFootDb = Depends(get_dbh)
):
    """
    Rerun multiple scans based on a comma-separated list of scan IDs.

    Returns:
        A dictionary indicating success and any necessary info (e.g., redirect URL).
    """
    ids_list = ids.split(",")
    cfg = deepcopy(state.config)
    modlist = []

    # List to store the IDs of newly started scans for the response
    new_scan_ids = []

    for id in ids_list:
        # 1. Get existing scan info
        info = dbh.scanInstanceGet(id)
        if not info:
            return jsonify_error(400, f"Invalid scan ID: {id}.")

        # 2. Get existing scan configuration
        scanconfig = dbh.scanConfigGet(id)
        scanname = info[0]
        scantarget = info[1]
        targetType = None

        if len(scanconfig) == 0:
            return jsonify_error(500, "Something went wrong internally: Scan configuration not found.")

        # 3. Process module list
        modlist = scanconfig['_modulesenabled'].split(',')
        if "sfp__stor_stdout" in modlist:
            modlist.remove("sfp__stor_stdout")

        # 4. Determine target type
        targetType = SpiderFootHelpers.targetTypeFromString(scantarget)
        if targetType is None:
            # Should never be triggered for a re-run scan..
            return jsonify_error(500, "Invalid target type. Could not recognize it as a target SpiderFoot supports.")

        # 5. Start running a new scan in a separate process
        scanId = SpiderFootHelpers.genScanInstanceId()
        try:
            # NOTE: mp.Process is a blocking operation, but the rest of the FastAPI
            # application remains responsive. The main concern is if 'dbh' calls (like in step 6)
            # are blocking, which should ideally be managed with `await asyncio.to_thread`
            # or `run_in_threadpool` if they take significant time.
            p = mp.Process(target=startSpiderFootScanner, args=(state.loggingQueue, scanname, scanId, scantarget, targetType, modlist, cfg))
            p.daemon = True
            p.start()
        except Exception as e:
            logger.error(f"[-] Scan [{scanId}] failed: {e}", exc_info=True)
            return jsonify_error(500, f"Scan [{scanId}] failed to start: {e}")

        # 6. Wait until the scan has initialized (Polling a blocking DB call)
        # This polling loop *blocks* the current FastAPI worker!
        # In a proper async implementation, this should be replaced with:
        # A) A non-blocking check (if the DB layer supports it)
        # B) Running the loop in an `asyncio.to_thread` and awaiting it,
        #    or preferably, having the client poll the status instead of the server blocking.
        # C) For now, we'll keep the logic but acknowledge the blocking nature:
        
        start_time = time.time()
        timeout = 10 # seconds
        while dbh.scanInstanceGet(scanId) is None:
            if time.time() - start_time > timeout:
                logger.error(f"[-] Scan [{scanId}] initialization timed out.", exc_info=True)
                return jsonify_error(500, f"Scan [{scanId}] initialization timed out.")
            logger.info("Waiting for the scan to initialize...")
            time.sleep(1) # Blocking sleep!

        new_scan_ids.append(scanId)

    # 7. Return success response
    return {
        "message": f"Successfully started re-run for scans. New IDs: {', '.join(new_scan_ids)}",
        "rerunscans": True,
        "redirect_page": "/scans", # Hypothetical redirect to scan list
    }
