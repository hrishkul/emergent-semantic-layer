"""A two-table imitation of the Kaggle workbooks, with planted defects on request."""

from pathlib import Path

import pandas as pd

from esl.sources import erp_mtdd


def write_workbooks(directory: Path, *, defects: bool = False) -> erp_mtdd.SourceFiles:
    customers = pd.DataFrame(
        {
            "Customer_ID": [1, 2, 3],
            "Customer_Name": ["Amman Steel", "Aqaba Freight", "Irbid Foods"],
            "Credit_Limit": [5000.0, None, 12000.5],
            "Is_Active": [True, True, False],
        }
    )
    orders = pd.DataFrame(
        {
            "Sales_Order_ID": [10, 11, 12, 13],
            "Customer_ID": [1, 2, 2, None],
            "Order_Date": ["2025-01-05", "2025-02-11", "2025-03-02", "2025-03-09"],
            "Total_Amount": [1160.0, 232.0, 58.0, 99.5],
        }
    )
    if defects:
        orders.loc[3, "Customer_ID"] = 99  # orphan
        orders.loc[2, "Sales_Order_ID"] = 11  # duplicate key
        customers = customers.rename(columns={"Is_Active": "Active_Flag"})  # drift
    seed = directory / erp_mtdd.SEED_FILE
    with pd.ExcelWriter(seed) as writer:
        pd.DataFrame([["ERP Seed Data"]]).to_excel(
            writer, sheet_name="Index", index=False, header=False
        )
        customers.to_excel(writer, sheet_name="Customers", index=False)
        orders.to_excel(writer, sheet_name="Sales Orders", index=False)

    docs = {
        "Table Index": pd.DataFrame(
            {"Table Name": ["Customers", "Sales Orders"],
             "Primary Key": ["Customer_ID", "Sales_Order_ID"]}
        ),
        "Dependency Register": pd.DataFrame({"Table Name": ["Sales Orders"]}),
        "Complexity Rules": pd.DataFrame({"Complexity": ["Low"], "Weight": [1]}),
        "Column Dictionary": pd.DataFrame(
            {
                "Table": ["Customers"] * 4 + ["Sales Orders"] * 4,
                "Column Name": ["Customer_ID", "Customer_Name", "Credit_Limit", "Is_Active",
                                "Sales_Order_ID", "Customer_ID", "Order_Date", "Total_Amount"],
                "Data Type": ["BIGINT", "VARCHAR(150)", "DECIMAL(18,2)", "BOOLEAN",
                              "BIGINT", "BIGINT", "DATE", "DECIMAL(18,2)"],
            }
        ),
        "Relationships": pd.DataFrame(
            {"Child Table": ["Sales Orders"], "Child Column": ["Customer_ID"],
             "Parent Table": ["Customers"], "Parent Key": ["Customer_ID"],
             "Optional?": ["Mandatory"], "Cross-module?": ["No"]}
        ),
        "Load Order": pd.DataFrame({"Order": [1, 2], "Table": ["Customers", "Sales Orders"]}),
    }
    schema = directory / erp_mtdd.SCHEMA_FILE
    with pd.ExcelWriter(schema) as writer:
        for name, frame in docs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return erp_mtdd.SourceFiles(seed=seed, schema=schema)
