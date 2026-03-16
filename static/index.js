function setDateWeek() {
    // // Previous Week
    // let d = new Date();

    // let month = d.getMonth() + 1;
    // let day = d.getDate();

    // let currentDate = d.getFullYear() + '-' +
    //     (month < 10 ? '0' : '') + month + '-' +
    //     (day < 10 ? '0' : '') + day;
    //     // console.log(currentDate)

    //     $("#endDate").val(currentDate)

    //     modifiedDay = d.getDate() -4;

    //     let modifiedDate = d.getFullYear() + '-' +
    //     (month < 10 ? '0' : '') + month + '-' +
    //     (modifiedDay < 10 ? '0' : '') + modifiedDay;
    //     // console.log(modifiedDate)

    //     $("#startDate").val(modifiedDate)


    let curr = new Date(); // get current date  
    let first = curr.getDate() - curr.getDay(); // First day is the  day of the month - the day of the week  
    let last = first + 6; // last day is the first day + 6   

    let firstday = new Date(curr.setDate(first)).toISOString().split('T')[0];
    let lastday = new Date(curr.setDate(curr.getDate() + 6)).toISOString().split('T')[0];

    $("#endDate").val(lastday)
    $("#startDate").val(firstday)
}

function setDateMonth() {
    // //Previous Month
    // let fullDate = new Date();
    // let year = fullDate.getFullYear();
    // // let twoDigitMonth = fullDate.getMonth() + "";
    // let twoDigitMonth = fullDate.getMonth() + 1 + "";

    // if (twoDigitMonth.length == 1) twoDigitMonth = "0" + twoDigitMonth;
    // let twoDigitDate = fullDate.getDate() + "";
    // if (twoDigitDate.length == 1) twoDigitDate = "0" + twoDigitDate;
    // let currentDate = year + "-" + (twoDigitMonth) + "-" + twoDigitDate;
    // // console.log("currendate:", currentDate);

    // $("#endDate").val(currentDate)

    // let modifiedDate;
    // if (twoDigitMonth = 01) {
    //     twoDigitMonth = 12;
    //     modifiedDate = year - 1 + "-" + twoDigitMonth + "-" + twoDigitDate;
    //     // console.log(modifiedDate)
    // } else {
    //     twoDigitMonth -= 1;
    //     modifiedDate = year + "-" + twoDigitMonth + "-" + twoDigitDate;
    //     // console.log(modifiedDate)
    // }


    // $("#startDate").val(modifiedDate)

    let date = new Date();
    let firstDay = new Date(date.getFullYear(), date.getMonth(), 1).toISOString().split('T')[0];
    let lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0).toISOString().split('T')[0];

    $("#startDate").val(firstDay)
    $("#endDate").val(lastDay)
}

function setDateYear() {
    // //Previous Year
    // let d = new Date();

    // let month = d.getMonth() + 1;
    // let day = d.getDate();

    // let currentDate = d.getFullYear() + '-' +
    //     (month < 10 ? '0' : '') + month + '-' +
    //     (day < 10 ? '0' : '') + day;
    // // console.log(currentDate)

    // $("#endDate").val(currentDate)

    // let modifiedDate = d.getFullYear() - 1 + '-' +
    //     (month < 10 ? '0' : '') + month + '-' +
    //     (day < 10 ? '0' : '') + day;
    // // console.log(modifiedDate)

    // $("#startDate").val(modifiedDate)

    let firstday = new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0];
    let lastday = new Date(new Date().getFullYear(), 11, 31).toISOString().split('T')[0];

    $("#startDate").val(firstday)
    $("#endDate").val(lastday)

}
// Function to determine whether a single user search is made or a team search
function getSelectedValue() {
    let selectedValue = document.getElementById("teams").value
    // console.log(selectedValue)
    if (selectedValue !== "Single") {
        $("#userId").val("")
        $("#userIdField").css("visibility", "hidden");
    } else {
        $("#userIdField").css("visibility", "visible");
    }
}
