# Create top-level compartments in ROOT compartment

locals {

    all_comp = {
        CLOUD-ENG = {
            name = "${var.engineer_compartment_base_name}",
            description = "Top level compartment for all cloud engineers",
        },
        SPECIAL-CMP = {
            name = "xx-${var.engineer_compartment_base_name}-projects", 
            description = "Special project compartments", 
        },
        SHARED-CMP = {
            name = "${var.engineer_compartment_base_name}-shared",
            description = "Shared compartment for all cloud engineers - limited access",
            children = {
                OAC-CMP = {
                    name = "OAC",
                    description = "Oracle Analytics Cloud"
                },
                OIC-CMP = {
                    name = "OIC",
                    description = "Oracle Integration Cloud"
                },
                EXACS-CMP = {
                    name = "ExaCS",
                    description = "Oracle Exadata Cloud Service"
                },
            }
        }
    }

    # Place any created compartments in the defined top compartment
    compartments_configuration = {
        default_parent_id : var.tenancy_ocid
        enable_delete : false
        compartments : local.all_comp
    }

}
