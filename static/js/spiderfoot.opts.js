activeTab = "global";
function saveSettings() {
    var retarr = {}
    $(":input").each(function(i) {
        retarr[$(this).attr('id')] = $(this).val();
    });

    $("#allopts").val(JSON.stringify(retarr));
}

function clearSettings() {
    $("#allopts").val("RESET");
}

function switchTab(tab) {
    $("#optsect_"+activeTab).hide();
    $("#optsect_"+tab).show();
    $("#tab_"+activeTab).removeClass("active");
    $("#tab_"+tab).addClass("active");
    activeTab = tab;
}

function getFile(elemId) {
  const elem = document.getElementById(elemId);
  if (!elem) {
    console.warn(`Element with id '${elemId}' not found.`);
    return;
  }
  
  try {
    elem.click();
  } catch (err) {
    console.error('Error triggering file input click:', err);
  }
}

$(document).ready(function() {
  $("#btn-save-changes").click(function() { saveSettings(); });
  $("#btn-import-config").click(function() { getFile("configFile"); return false; });
  $("#btn-reset-settings").click(function() { console.log('reset'); clearSettings(); });
  $("#btn-opt-export").click(function() { window.location.href="optsexport?pattern=api_key"; return false; });
  $("#tab_global").click(function() { switchTab("global"); });
});

$(function () {
  $('[data-toggle="popover"]').popover()
  $('[data-toggle="popover"]').on("show.bs.popover", function() { $(this).data("bs.popover").tip().css("max-width", "600px") });
});
