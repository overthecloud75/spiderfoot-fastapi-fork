document.addEventListener("DOMContentLoaded", () => {
  const themeToggler = document.getElementById("theme-toggler");
  const head = document.getElementsByTagName("HEAD")[0];
  const togglerText = document.getElementById("toggler-text");
  let link = document.createElement("link");

  if (localStorage.getItem("mode") === "Light Mode") {
    togglerText.innerText = "Dark Mode";
    document.getElementById("theme-toggler").checked = true; // ensure theme toggle is set to dark
  } else { // initial mode ist null
    togglerText.innerText = "Light Mode";
    document.getElementById("theme-toggler").checked = false; // ensure theme toggle is set to light
  }


  themeToggler.addEventListener("click", () => {
    togglerText.innerText = "Light Mode";

    if (localStorage.getItem("theme") === "dark-theme") {
      localStorage.removeItem("theme");
      localStorage.setItem("mode", "Dark Mode");
      link.rel = "stylesheet";
      link.type = "text/css";
      link.href = "static/css/spiderfoot.css";

      head.appendChild(link);
      location.reload();
    } else {
      localStorage.setItem("theme", "dark-theme");
      localStorage.setItem("mode", "Light Mode");
      link.rel = "stylesheet";
      link.type = "text/css";
      link.href = "static/css/dark.css";

      head.appendChild(link);
      location.reload();
    }
  });
});

var sf = {};

sf.replace_sfurltag = function (data) {
  if (data.toLowerCase().indexOf("&lt;sfurl&gt;") >= 0) {
    data = data.replace(
      RegExp("&lt;sfurl&gt;(.*)&lt;/sfurl&gt;", "img"),
      "<a target=_new href='$1'>$1</a>"
    );
  }
  if (data.toLowerCase().indexOf("<sfurl>") >= 0) {
    data = data.replace(
      RegExp("<sfurl>(.*)</sfurl>", "img"),
      "<a target=_new href='$1'>$1</a>"
    );
  }
  return data;
};

sf.remove_sfurltag = function (data) {
  if (data.toLowerCase().indexOf("&lt;sfurl&gt;") >= 0) {
    data = data
      .toLowerCase()
      .replace("&lt;sfurl&gt;", "")
      .replace("&lt;/sfurl&gt;", "");
  }
  if (data.toLowerCase().indexOf("<sfurl>") >= 0) {
    data = data.toLowerCase().replace("<sfurl>", "").replace("</sfurl>", "");
  }
  return data;
};

sf.search = function (scan_id, value, type, postFunc) {
  sf.fetchData(
    "api/search",
    { id: scan_id, eventType: type, value: value },
    postFunc
  );
};

sf.deleteScan = async function(scan_id, callback) {
  try {
    const response = await fetch(`/api/scandelete?id=${scan_id}`, {
        method: "GET",
    });

    const data = await response.json(); 
    if (!response.ok) {
        alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Error</b><br/><br/>${data.message}`);
        return;
    }
    alertify.success(`<i class="bi bi-check-circle-fill"></i> <b>Scans Deleted</b><br/><br/>${scan_id.replace(/,/g, "<br/>")}`);
    if (callback) callback();
  } catch (err) {
      alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Network Error</b><br/><br/>${err}`);
  }
};

sf.stopScan = async function(scan_id, callback) {
  try {
      const response = await fetch(`/api/stopscan?id=${scan_id}`, {
          method: "GET",
      });

      const data = await response.json(); 

      if (!response.ok) {
          alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Error</b><br/><br/>${data.message}`);
          return;
      }
      alertify.success(`<i class="bi bi-check-circle-fill"></i> <b>Scans Aborted</b><br/><br/>${scan_id.replace(/,/g, "<br/>")}`);
      if (callback) callback();
  } catch (err) {
      alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Network Error</b><br/><br/>${err}`);
  }
};

sf.rerunScan = async function(scan_ids, callback) {
  try {
      const response = await fetch(`/api/rerunscanmulti?ids=${scan_ids}`, {
          method: "GET",
      });

      const data = await response.json(); 

      if (!response.ok) {
          alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Error</b><br/><br/>${data.message || "Unknown error"}`);
          return;
      }
      alertify.success(`<i class="bi bi-check-circle-fill"></i> <b>Rerun started</b><br/><br/>` + (data.message ? data.message : scan_ids.replace(/,/g, "<br/>")));
      if (callback) callback();
  } catch (err) {
      alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Network Error</b><br/><br/>${err}`);
  }
};

sf.fetchData = async function (url, postData, postFunc) {
  try {
      const response = await fetch(url, {
          method: "POST",
          headers: {
              "Content-Type": "application/json",
          },
          body: JSON.stringify(postData),
          cache: "no-store",
      });

      const data = await response.json(); 
      if (!response.ok) {
          alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Error</b><br/>${data.message}`);
          return;
      }

      if (postFunc) postFunc(data);
  } catch (err) {
      alertify.error(`<i class="bi bi-x-circle-fill"></i> <b>Network Error</b><br/>${err}`);
  }
};

/*
sf.simpleTable = function(id, data, cols, linkcol=null, linkstring=null, sortable=true, rowfunc=null) {
	var table = "<table id='" + id + "' ";
	table += "class='table table-bordered table-striped tablesorter'>";
	table += "<thead><tr>";
	for (var i = 0; i < cols.length; i++) {
		table += "<th>" + cols[i] + "</th>";
	}
	table += "</tr></thead><tbody>";

	for (var i = 1; i < data.length; i++) {
		table += "<tr>";
		for (var c = 0; c < data[i].length; c++) {
			if (c == linkcol) {
				if (linkstring.indexOf("%%col") > 0) {
				}
				table += "<td>" + <a class='link' onClick='" + linkstring + "'>";
				table += data[i][c] + "</a></td>"
			} else {
				table += "<td>" + data[i][c] + "</td>";
			}
		}
		table += "</tr>";
	}
	table += "</tbody></table>";

	return table;
}

*/

sf.updateBsTooltips = function(root = document) {
  const triggers = root.querySelectorAll('[data-bs-toggle="tooltip"]');
  triggers.forEach(el => {
    // 1️⃣ 기존 Tooltip이 있으면 제거
    const t = bootstrap.Tooltip.getInstance(el);
    if (t) t.dispose();
    // 2️⃣ 새 Tooltip 생성
    new bootstrap.Tooltip(el, { container: 'body' });
  });
};
