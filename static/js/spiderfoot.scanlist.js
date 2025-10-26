globalTypes = null;
globalFilter = null;
lastChecked = null;

function switchSelectAll() {
    if (!$("#checkall")[0].checked) {
        $("input[id*=cb_]").prop('checked', false);
    } else {
        $("input[id*=cb_]").prop('checked', true);
    }
}

function filter(type) {
    if (type == "all") {
        showlist();
        return;
    }
    if (type == "running") {
        showlist(["RUNNING", "STARTING", "STARTED", "INITIALIZING"], "Running");
        return;
    }
    if (type == "finished") {
        showlist(["FINISHED"], "Finished");
        return;
    }
    if (type == "failed") {
        showlist(["ABORTED", "FAILED"], "Failed/Aborted");
        return;
    }
}

function getSelected() {
    ids = [];
    $("input[id*=cb_]").each(function(i, obj) {
        if (obj.checked) {
            ids[ids.length] = obj.id.replace("cb_", "");
        }
    });

    if (ids.length == 0)
        return false;

    return ids;
}

function stopScan(id) {
    alertify.confirm("Are you sure you wish to stop this scan?",
    function(){
        sf.stopScan(id, reload);
    }).set({title:"Stop scan?"});
}

function stopSelected() {
    ids = getSelected();
    if (!ids) {
        alertify.message("Could not stop scans. No scans selected.");
        return;
    }

    alertify.confirm("Are you sure you wish to stop these " + ids.length + " scans?<br/><br/>" + ids.join("<br/>"),
    function(){
        sf.stopScan(ids.join(','), reload);
    }).set({title:"Stop scans?"});
}

function deleteScan(id) {
    alertify.confirm("Are you sure you wish to delete this scan?",
    function(){
        sf.deleteScan(id, reload);
    }).set({title:"Delete scan?"});
}

function deleteSelected() {
    ids = getSelected();
    if (!ids) {
        alertify.message("Could not delete scans. No scans selected.");
        return;
    }

    alertify.confirm("Are you sure you wish to delete these " + ids.length + " scans?<br/><br/>" + ids.join("<br/>"),
    function(){
        sf.deleteScan(ids.join(','), reload);
    }).set({title:"Delete scans?"});
}

function rerunSelected() {
    ids = getSelected();
    if (!ids) {
        alertify.message("Could not re-run scan. No scans selected.");
        return;
    }

    sf.rerunScan(ids, reload);
}

function exportSelected(type) {
    ids = getSelected();

    if (!ids) {
        return;
    }

    $("#loader").show();
    var efr = document.getElementById('exportframe');
    switch(type) {
        case "gexf":
            efr.src = 'scanvizmulti?ids=' + ids.join(',');
            break;
        case "csv":
            efr.src = 'scaneventresultexportmulti?ids=' + ids.join(',');
            break;
        case "excel":
            efr.src = 'scaneventresultexportmulti?filetype=excel&ids=' + ids.join(',');
            break;
        case "json":
            efr.src = 'scanexportjsonmulti?ids=' + ids.join(',');
            break;
        default:
    }
    $("#loader").fadeOut(500);
}

function reload() {
    $("#loader").show();
    showlist(globalTypes, globalFilter);
    return;
}

function showlist(types, filter) {
    globalTypes = types;
    globalFilter = filter;

    sf.fetchData('api/scanlist', null, function (data) {
        if (data.length === 0) {
            $("#loader").fadeOut(500);

            // Bootstrap 5 스타일 알림창
            let welcome = `
                <div class="alert alert-info d-flex align-items-start" role="alert">
                  <div>
                    <h4 class="alert-heading mb-2">No scan history</h4>
                    <p class="mb-0">
                      There is currently no history of previously run scans.
                      Please click <strong>“New Scan”</strong> to initiate a new scan.
                    </p>
                  </div>
                </div>
            `;

            $("#scancontent").append(welcome);
            return;
        }

        showlisttable(types, filter, data);
    });
}

function showlisttable(types, filter, data) {
    if (filter == null) filter = "None";

    let buttons = `
    <div class="btn-toolbar mb-3 d-flex justify-content-between">
      <div class="btn-group">
        <button id="btn-filter" class="btn btn-outline-secondary">
          <i class="bi bi-funnel"></i>&nbsp;Filter: ${filter}
        </button>
        <button class="btn btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false"></button>
        <ul class="dropdown-menu">
          <li><a class="dropdown-item" href="javascript:filter('all')">None</a></li>
          <li><a class="dropdown-item" href="javascript:filter('running')">Running</a></li>
          <li><a class="dropdown-item" href="javascript:filter('finished')">Finished</a></li>
          <li><a class="dropdown-item" href="javascript:filter('failed')">Failed/Aborted</a></li>
        </ul>
      </div>

      <div class="btn-group">
        <button data-bs-toggle='tooltip' data-bs-title="Re-run Selected" id="btn-rerun" class="btn btn-outline-secondary">
          <i class="bi bi-arrow-repeat"></i>
        </button>
        <button data-bs-toggle='tooltip' data-bs-title="Stop Selected" id="btn-stop" class="btn btn-outline-secondary me-2">
          <i class="bi bi-stop-circle"></i>
        </button>
        <button data-bs-toggle='tooltip' data-bs-title="Refresh" id="btn-refresh" class="btn btn-success">
          <i class="bi bi-arrow-clockwise"></i>
        </button>
        <button data-bs-toggle="tooltip" data-bs-title="Export Selected" id="btn-export" class="btn btn-success me-2">
          <i class="bi bi-download"></i>
        </button>
        <ul class="dropdown-menu">
          <li><a class="dropdown-item" href="javascript:exportSelected('csv')">CSV</a></li>
          <li><a class="dropdown-item" href="javascript:exportSelected('excel')">Excel</a></li>
        </ul>
        <button data-bs-toggle='tooltip' data-bs-title="Delete Selected" id="btn-delete" class="btn btn-danger">
            <i class="bi bi-trash"></i>
        </button>
      </div>
    </div>
    `;

    let table = `
    <table id="scanlist" class="table table-bordered table-striped align-middle">
      <thead class="table-light">
        <tr>
          <th class="text-center"><input id="checkall" type="checkbox"></th>
          <th>Name</th>
          <th>Target</th>
          <th>Started</th>
          <th>Finished</th>
          <th class="text-center">Status</th>
          <th class="text-center">Elements</th>
          <th class="text-center">Correlations</th>
          <th class="text-center">Action</th>
        </tr>
      </thead>
      <tbody>
    `;
    for (let i = 0; i < data.length; i++) {
        let status = data[i].status;
        let statusClass = "bg-info text-dark";

        if (types != null && $.inArray(status, types)) {
            continue;
        }   

        if (status === "FINISHED") statusClass = "bg-success text-white";
        else if (status.indexOf("ABORT") >= 0) statusClass = "bg-warning text-dark";
        else if (status.indexOf("FAILED") >= 0) statusClass = "bg-danger text-white";

        table += `
        <tr>
          <td class="text-center"><input type="checkbox" id="cb_${data[i].id}"></td>
          <td><a href="scaninfo?id=${data[i].id}">${data[i].name}</a></td>
          <td>${data[i].target}</td>
          <td>${data[i].created}</td>
          <td>${data[i].finished}</td>
          <td class="text-center"><span class="badge ${statusClass}">${status}</span></td>
          <td class="text-center">${data[i].progress}</td>
          <td class="text-center">
            <span class="badge bg-danger">${data[i].risk_matrix['HIGH']}</span>
            <span class="badge bg-warning text-dark">${data[i].risk_matrix['MEDIUM']}</span>
            <span class="badge bg-info text-dark">${data[i].risk_matrix['LOW']}</span>
            <span class="badge bg-success">${data[i].risk_matrix['INFO']}</span>
          </td>
          <td class="text-center">
        `;

        if (status === "RUNNING" || status === "STARTING" || status === "STARTED" || status === "INITIALIZING") {
            table += `<a data-bs-toggle="tooltip" data-bs-title="Stop Scan" href="javascript:stopScan('${data[i].id}')"><i class="bi bi-stop text-muted"></i></a>`;
        } else {
            table += `
              <a data-bs-toggle="tooltip" data-bs-title="Delete Scan" href="javascript:deleteScan('${data[i].id}')"><i class="bi bi-trash text-muted"></i></a>
              &nbsp;&nbsp;<a data-bs-toggle="tooltip" data-base-title="Re-run Scan" href="api/rerunscan?id=${data[i].id}"><i class="bi bi-arrow-repeat text-muted"></i></a>
            `;
        }

        table += `
          &nbsp;&nbsp;<a data-bs-toggle="tooltip" data-bs-title="Clone Scan" href="clonescan?id=${data[i].id}"><i class="bi bi-plus-circle text-muted"></i></a>
          </td>
        </tr>
        `;
    }

    table += `
    </tbody>
    <tfoot>
    <tr>
        <th colspan="9" class="ts-pager form-inline">
        <div class="d-flex align-items-center flex-nowrap gap-2 w-100">
            <!-- 이전/처음 버튼 그룹 -->
            <div class="btn-group btn-group-sm">
            <button type="button" class="btn btn-outline-secondary first">
                <i class="bi bi-skip-backward-fill"></i>
            </button>
            <button type="button" class="btn btn-outline-secondary prev">
                <i class="bi bi-rewind-fill"></i>
            </button>
            </div>

            <!-- 다음/마지막 버튼 그룹 -->
            <div class="btn-group btn-group-sm">
            <button type="button" class="btn btn-outline-secondary next">
                <i class="bi bi-fast-forward-fill"></i>
            </button>
            <button type="button" class="btn btn-outline-secondary last">
                <i class="bi bi-skip-forward-fill"></i>
            </button>
            </div>

            <!-- 페이지 크기 선택 -->
            <select class="form-select form-select-sm pagesize" title="Select page size">
            <option selected value="10">10</option>
            <option value="20">20</option>
            <option value="30">30</option>
            <option value="all">All Rows</option>
            </select>

            <!-- 페이지 번호 선택 -->
            <select class="form-select form-select-sm pagenum" title="Select page number"></select>

            <!-- 페이지 표시 -->
            <span class="pagedisplay ms-auto"></span>
        </div>
        </th>
    </tr>
    </tfoot>
    </table>
    `;

    $("#loader").fadeOut(500);
    $("#scancontent-wrapper").remove();
    $("#scancontent").append("<div id='scancontent-wrapper'> " + buttons + table + "</div>");
    sf.updateBsTooltips();
    $("#scanlist").tablesorter().tablesorterPager({
      container: $(".ts-pager"),
      cssGoto: ".pagenum",
      output: 'Scans {startRow} - {endRow} / {filteredRows} ({totalRows})'
    });

    $(document).ready(function() {
        var chkboxes = $('input[id*=cb_]');
        chkboxes.click(function(e) {
            if(!lastChecked) {
                lastChecked = this;
                return;
            }

            if(e.shiftKey) {
                var start = chkboxes.index(this);
                var end = chkboxes.index(lastChecked);

                chkboxes.slice(Math.min(start,end), Math.max(start,end)+ 1).prop('checked', lastChecked.checked);
            }

            lastChecked = this;
        });

        $("#btn-delete").click(function() { deleteSelected(); });
        $("#btn-refresh").click(function() { reload(); });
        $("#btn-rerun").click(function() { rerunSelected(); });
        $("#btn-stop").click(function() { stopSelected(); });
        $("#checkall").click(function() { switchSelectAll(); });
    });
}

showlist();

