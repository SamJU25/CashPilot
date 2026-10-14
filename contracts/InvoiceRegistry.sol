// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

/**
 * @title InvoiceRegistry
 * @dev Consortium blockchain registry for B2B e-invoices on FISCO BCOS.
 * Prevents double-financing across lenders via PBFT consensus.
 * Aligns with docs/system.md Section 6.1.
 */
contract InvoiceRegistry {
    enum Status { UNREGISTERED, PLEDGED, SETTLED }

    struct InvoiceRecord {
        bytes32 invoiceHash;
        uint256 lenderId;
        uint256 pledgedTimestamp;
        Status status;
    }

    // Mapping from canonical invoice SHA-256 hash to its on-chain status
    mapping(bytes32 => InvoiceRecord) public registry;

    event InvoicePledged(bytes32 indexed invoiceHash, uint256 indexed lenderId, uint256 timestamp);
    event InvoiceSettled(bytes32 indexed invoiceHash, uint256 timestamp);

    /**
     * @dev Pledges an invoice to a specific lender. Reverts if already pledged or settled.
     * @param invoiceHash Canonical hash of (tax_id, buyer_id, invoice_num, amount_cents)
     * @param lenderId Unique ID of the lending institution
     */
    function pledgeInvoice(bytes32 invoiceHash, uint256 lenderId) external {
        InvoiceRecord storage record = registry[invoiceHash];
        require(record.status == Status.UNREGISTERED, "ERR_INVOICE_ALREADY_PLEDGED");
        
        record.invoiceHash = invoiceHash;
        record.lenderId = lenderId;
        record.pledgedTimestamp = block.timestamp;
        record.status = Status.PLEDGED;

        emit InvoicePledged(invoiceHash, lenderId, block.timestamp);
    }

    /**
     * @dev Settles an invoice upon full loan repayment.
     * @param invoiceHash Canonical hash of the invoice
     */
    function settleInvoice(bytes32 invoiceHash) external {
        InvoiceRecord storage record = registry[invoiceHash];
        require(record.status == Status.PLEDGED, "ERR_INVOICE_NOT_PLEDGED");
        
        record.status = Status.SETTLED;
        emit InvoiceSettled(invoiceHash, block.timestamp);
    }

    /**
     * @dev Query the status of an invoice.
     * @param invoiceHash Canonical hash of the invoice
     */
    function getInvoiceStatus(bytes32 invoiceHash) external view returns (Status, uint256, uint256) {
        InvoiceRecord storage record = registry[invoiceHash];
        return (record.status, record.lenderId, record.pledgedTimestamp);
    }
}
